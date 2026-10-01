"""List patch ids in W. Stevens' public Scroll 4 zips by HTTP range reads of the zip central directory (no bulk download).
Usage: python zip_listing.py s4_good_patches s4_bad_patches  -> <name>_ids.txt + one summary line per zip."""
import io, re, sys, zipfile, urllib.request, collections
class R(io.RawIOBase):
    def __init__(s,u):
        s.u=u; s.p=0; h=urllib.request.urlopen(urllib.request.Request(u,method="HEAD")); s.n=int(h.headers["Content-Length"]); s.lm=h.headers.get("Last-Modified")
    def seekable(s): return True
    def readable(s): return True
    def tell(s): return s.p
    def seek(s,o,w=0):
        s.p={0:o,1:s.p+o,2:s.n+o}[w]; return s.p
    def readinto(s,b):
        if s.p>=s.n: return 0
        e=min(s.n,s.p+len(b))-1
        d=urllib.request.urlopen(urllib.request.Request(s.u,headers={"Range":f"bytes={s.p}-{e}"})).read()
        b[:len(d)]=d; s.p+=len(d); return len(d)
for lab in sys.argv[1:]:
    u=f"https://dl.ash2txt.org/community-uploads/will/{lab}.zip"; r=R(u)
    z=zipfile.ZipFile(io.BufferedReader(r,1<<20))
    files=collections.defaultdict(set); other=collections.Counter()
    for m in z.infolist():
        g=re.match(r"[^/]+/patch_(\d+)/([^/]+)$",m.filename)
        if g: files[int(g.group(1))].add(g.group(2))
        else: other[m.filename.split('/')[0]+'/…' if '/' in m.filename else m.filename]+=1
    full=[i for i,f in files.items() if {"x.tif","y.tif","z.tif","meta.json"}<=f]
    open(f"{lab}_ids.txt","w").write("\n".join(map(str,sorted(files))))
    print(lab, "bytes",r.n,"last-modified",r.lm,"members",len(z.infolist()),"patch dirs",len(files),"complete(x,y,z,meta)",len(full),"other",dict(other.most_common(5)))
