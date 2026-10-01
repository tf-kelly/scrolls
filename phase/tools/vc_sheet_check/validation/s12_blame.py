#!/usr/bin/env python3
"""S1, S2 (S12_PROTOCOL.md): Stevens' removals vs our flags on the SessA-15 Scroll 4 whole-scroll index.
Usage: s12_blame.py WRAP_INDEX_CSV UNSATISFIED_CSV GOOD_ZIP BAD_ZIP OUT.json"""
import heapq, json, re, sys, zipfile

import pandas as pd


def labels(gz, bz):
    L = {}
    for zn, lab in ((gz, "kept"), (bz, "removed")):
        for n in zipfile.ZipFile(zn).namelist():
            m = re.search(r"(?:^|/)patch_(\d+)/x\.tif$", n)
            if m: L[int(m.group(1))] = lab
    return L


def greedy_min_id(pairs):
    """Remove the patch in the most remaining pairs; ties -> smallest id (coordinator's text)."""
    adj = {}
    for a, b in pairs: adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
    h = [(-len(v), p) for p, v in adj.items()]; heapq.heapify(h); bad = []
    while h:
        d, p = heapq.heappop(h)
        if p not in adj or -d != len(adj[p]) or not adj[p]:
            if p in adj and adj[p] and -d != len(adj[p]): heapq.heappush(h, (-len(adj[p]), p))
            continue
        bad.append(p)
        for q in adj.pop(p):
            adj[q].discard(p)
            if adj[q]: heapq.heappush(h, (-len(adj[q]), q))
    return bad


def greedy_his(pairs):
    """badpatchfinder.cpp FindBadPatches 186-222 as in phase/writeup/w2_stats.py greedy() (running count, list order)."""
    pairs = list(pairs); bad = []
    while pairs:
        freq, hf, hp = {}, -1, -1
        for a, b in pairs:
            freq[a] = freq.get(a, 0) + 1; freq[b] = freq.get(b, 0) + 1
            if hf == -1 or freq[a] > hf: hf, hp = freq[a], a
            if freq[b] > hf: hf, hp = freq[b], b
        bad.append(hp); pairs = [(a, b) for a, b in pairs if a != hp and b != hp]
    return bad


def table(ours, L, pop):
    ours = set(ours); t = {}
    for p in pop:
        t[(p in ours, L[p] == "removed")] = t.get((p in ours, L[p] == "removed"), 0) + 1
    both, ours_only, his_only, neither = t.get((True, True), 0), t.get((True, False), 0), t.get((False, True), 0), t.get((False, False), 0)
    n = both + ours_only + his_only + neither; po = (both + neither) / n
    pe = ((both + ours_only) * (both + his_only) + (his_only + neither) * (ours_only + neither)) / n / n
    his_rem, his_kept = both + his_only, ours_only + neither
    return dict(both_bad=both, ours_only=ours_only, his_only=his_only, both_good=neither, cohen_kappa=round((po - pe) / (1 - pe), 4),
                agreement_on_his_removed=round(both / his_rem, 4), ours_bad_among_his_kept=round(ours_only / his_kept, 4),
                precision_ours_vs_his=round(both / max(both + ours_only, 1), 4), our_bad_list_size=len(ours))


def main():
    wif, unf, gz, bz, out = sys.argv[1:6]
    pop = sorted(pd.read_csv(wif).patch.astype(int)); L = labels(gz, bz); popset = set(pop)
    missing = [p for p in pop if p not in L]; assert not missing, f"{len(missing)} indexed patches without a zip label"
    un = pd.read_csv(unf); J = sorted({tuple(sorted((int(a), int(b)))) for a, b in zip(un.patch_a, un.patch_b)})
    J = [j for j in J if j[0] in popset and j[1] in popset]
    flagged = {p for j in J for p in j}; kept_flagged = [p for p in flagged if L[p] == "kept"]
    nbr = {}
    for a, b in J: nbr.setdefault(a, set()).add(b); nbr.setdefault(b, set()).add(a)
    s1 = sum(any(L[q] == "removed" for q in nbr[p]) for p in kept_flagged)
    res = dict(population=len(pop), his_removed=sum(L[p] == "removed" for p in pop), his_kept=sum(L[p] == "kept" for p in pop),
               unsatisfied_joins=len(J), flagged_by_us=len(flagged),
               S1=dict(flagged_and_his_kept=len(kept_flagged), with_unsat_join_to_his_removed=s1, share=round(s1 / len(kept_flagged), 4),
                       baseline_share_of_removed_among_all_flagged_neighbours=round(sum(L[q] == "removed" for p in kept_flagged for q in nbr[p]) / sum(len(nbr[p]) for p in kept_flagged), 4)))
    ours = greedy_min_id(J); res["S2_primary_ties_min_id"] = table(ours, L, pop)
    ours_h = greedy_his(J); res["S2_sensitivity_his_tie_rule"] = table(ours_h, L, pop)
    res["S2_lists_identical"] = set(ours) == set(ours_h)
    res["flagged_any_unsat_vs_his"] = table(flagged, L, pop)   # context: every flagged patch, no greedy
    json.dump(dict(protocol="S12_PROTOCOL.md", results=res, our_bad_list=sorted(ours)), open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
