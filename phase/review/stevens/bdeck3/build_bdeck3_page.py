"""Reader page for blind deck 3, masked middle (PREREG.md, c0823fb). The page never reads the sealed key.
  build_bdeck3_page.py DECK_DIR OUT_DIR      -> OUT_DIR/bdeck3.html + img/<id>.png; exports responses_bdeck3.json
Reading conditions are stated by the reader first, nothing pre-filled (VP-M18). One frame at a time in the committed
order, no going back, zoom 2x at most. Storage: db (owner-only rules at publish) + browser draft; export via downloads.
"""
import json, shutil, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "deck6"))
import build_pages as B   # noqa: E402

deck, out = Path(sys.argv[1]), Path(sys.argv[2]); (out / "img").mkdir(parents=True, exist_ok=True)
D = json.load(open(deck / "deck.json")); items = [{"item": o["id"], "sha256": o["sha256"]} for o in D["order"]]
for it in items: shutil.copy(deck / f"{it['item']}.png", out / "img" / f"{it['item']}.png")
NOTICE = ("Scroll 4 (PHerc 1667) upstream data. Pages: patches grown and aligned by W. Stevens (report12), "
          "community-uploads/will; order = our index. Private; not for release.")
PAGE = r"""<title>Sheet Match Deck 3</title>
__STYLE__
<div class="wrap">
  <header class="bar"><h1>Deck 3: same sheet or different?</h1><div class="progress" id="progress"></div></header>
  <p class="notice">__NOTICE__</p>
  <details class="brief" open><summary>How this works</summary><ul>
    <li>__N__ CT cross-sections of Scroll 4, each 301 &times; 121 voxels (about 2.4 &times; 1.0 mm) shown at 2 screen px per voxel, one contrast setting for all. The thin yellow line is one of Stevens' pages where it crosses the section, placed by computation.</li>
    <li>The yellow line is drawn only near the left and right edges; the middle of each frame shows the CT alone. For each: <b>are the left and right yellow segments on the same sheet?</b> Answer same sheet, different sheet, or can't tell. A note is optional.</li>
    <li>One at a time; <b>no going back</b>. Zoom is limited to 2&times;. The frames carry no labels or marks; what each one is stays in a sealed key, opened only after your answers are committed.</li></ul></details>
  <div id="condbox"></div>
  <section class="viewer" id="viewer" hidden>
    <div class="sid" id="sid"></div>
    <div class="tools"><label><input type="checkbox" id="zoom"> Zoom 2&times;</label></div>
    <div class="ctbox" id="box"><img id="img" alt="CT cross-section with a yellow line"></div>
    <p class="q">Are the left and right yellow segments on the same sheet?</p>
    <div class="opts"><button type="button" class="opt" data-a="same">Same sheet</button><button type="button" class="opt" data-a="different">Different sheet</button><button type="button" class="opt" data-a="cant">Can't tell</button></div>
    <label class="note">Note (optional)<textarea id="note" rows="2"></textarea></label>
    <div class="nav"><span class="status" id="hint"></span><button type="button" class="primary" id="next" disabled>Confirm and next</button></div>
  </section>
  <section class="panel"><h2>Save</h2><div class="save"><button type="button" class="primary" id="export">Save responses_bdeck3.json</button><button type="button" id="copy">Copy JSON</button></div>
    <p class="status" id="status">Answers save as you go (<span id="storeword">checking storage…</span>).</p><textarea id="json" hidden rows="6" style="width:100%"></textarea></section>
</div>
<style>#box{overflow:auto}#box img{width:602px;max-width:100%;image-rendering:pixelated}#box.z img{width:1204px;max-width:none}</style>
<script>
__COND__
const ITEMS = __ITEMS__; const KEY = "bdeck3-responses-v1";
let S = {}; try { S = JSON.parse(localStorage.getItem(KEY) || "{}") || {}; } catch (e) {}
S.cond = S.cond || {}; S.ans = S.ans || {}; S.opened_at = S.opened_at || new Date().toISOString();
let db = null, pend = {}; const $ = id => document.getElementById(id); let tm = null;
function persist(){ S.changed_at = new Date().toISOString(); try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {}
  if (!db) return; clearTimeout(tm); tm = setTimeout(async () => { try { await db.doc("responses/bdeck3").set(S); } catch (e) {} }, 300); }
const cur = () => ITEMS.findIndex(it => !S.ans[it.item]);
function render(){
  $("condbox").innerHTML = S.cond.model_output_seen && S.started_at ? "" : condHTML(S.cond) + `<section class="panel"><button type="button" class="opt" id="start" ${S.cond.model_output_seen ? "" : "disabled"}>Start the deck</button></section>`;
  document.querySelectorAll("[data-cond]").forEach(b => b.onclick = () => { S.cond.model_output_seen = b.dataset.cond; S.cond.stated_at = new Date().toISOString(); persist(); render(); });
  const cn = $("condnote"); if (cn) cn.oninput = e => { S.cond.note = e.target.value; persist(); };
  const st = $("start"); if (st) st.onclick = () => { S.started_at = new Date().toISOString(); persist(); render(); };
  const k = cur(); const n = Object.keys(S.ans).length; $("progress").textContent = `${n} / ${ITEMS.length}`;
  if (!S.started_at || k < 0){ $("viewer").hidden = true; if (k < 0 && S.started_at) $("status").textContent = `All ${ITEMS.length} answered. Save the file and send it.`; return; }
  $("viewer").hidden = false; const it = ITEMS[k]; $("sid").textContent = `Frame ${k + 1} of ${ITEMS.length}`;
  if ($("img").dataset.item !== it.item){ $("img").src = `img/${it.item}.png`; $("img").dataset.item = it.item; pend = {shown_at: new Date().toISOString()}; $("note").value = ""; }
  document.querySelectorAll("[data-a]").forEach(b => b.setAttribute("aria-pressed", String(pend.answer === b.dataset.a)));
  $("next").disabled = !pend.answer; $("hint").textContent = $("next").disabled ? "Choose one answer." : "";
}
document.querySelectorAll("[data-a]").forEach(b => b.onclick = () => { pend.answer = b.dataset.a; render(); });
$("zoom").oninput = () => $("box").classList.toggle("z", $("zoom").checked);
$("next").onclick = () => { const it = ITEMS[cur()]; S.ans[it.item] = Object.assign({}, pend, {note: $("note").value, answered_at: new Date().toISOString()}); persist(); $("zoom").checked = false; $("box").classList.remove("z"); render(); };
const doc = () => ({deck: "bdeck3", instrument: "phase/review/stevens/bdeck3/build_bdeck3_page.py", exported: new Date().toISOString(), reader: "Thomas",
  conditions_stated_by_reader: S.cond, page_opened_at: S.opened_at, started_at: S.started_at || null,
  answers: ITEMS.map(it => Object.assign({item: it.item, image_sha256: it.sha256}, S.ans[it.item] || {answer: null}))});
$("copy").onclick = async () => { const s = JSON.stringify(doc(), null, 1); try { await navigator.clipboard.writeText(s); $("status").textContent = "Copied."; } catch (e) { $("json").hidden = false; $("json").value = s; $("json").select(); } };
render();
(async () => { const dl = await window.claude?.use?.("downloads"); if (!dl){ $("export").hidden = true; return; }
  $("export").onclick = async () => { try { await dl.save({filename: "responses_bdeck3.json", data: JSON.stringify(doc(), null, 1)}); $("status").textContent = "Saved. Send it; it is committed unchanged before the key is opened."; }
    catch (e) { $("status").textContent = e && e.code === "declined" ? "Save cancelled." : "Saving is not available here; use Copy JSON."; } }; })();
(async () => { db = await window.claude?.use?.("db"); if (!db){ $("storeword").textContent = "in this browser only"; return; }
  $("storeword").textContent = "to this page";
  try { const d = await db.doc("responses/bdeck3").get(); const v = d.data(); if (v && Object.keys(v.ans || {}).length >= Object.keys(S.ans).length) { S = Object.assign(S, v); render(); } } catch (e) {} })();
</script>
"""
(out / "bdeck3.html").write_text(PAGE.replace("__N__", str(len(items))).replace("__STYLE__", B.STYLE).replace("__NOTICE__", NOTICE)
                                .replace("__ITEMS__", json.dumps(items)).replace("__COND__", B.COND_JS))
print(len(items), "deck items")
