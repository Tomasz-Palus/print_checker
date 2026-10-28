import sys, os, json
sys.path.insert(0, "/home/user/print_checker/narzedzia"); sys.path.insert(0, "/home/user/print_checker/app")
import test_projektu as T, porownaj_silniki as P, pymupdf
from PIL import Image
D = "szablony"; GL = {"1000": "a" * 32, "100": "b" * 32}
def look(f):
    r = pymupdf.open(f)[0].rect
    return P.gs_render(f, 0, 900 / max(r.width, r.height), True, None, r)
ref = look(f"{D}/01_czysty.pdf")
for name in sorted(os.listdir(D)):
    if name.startswith("_"): continue
    j = T.upload(f"{D}/{name}"); jid = j["job_id"]; mm = j["file"]["pages"][0]["width_mm"]
    gl = GL["100" if mm < 200 else "1000"]
    fr = T.req(f"/api/jobs/{jid}/frames?page=0&gl={gl}&glpage=1")
    line = f"{name:40} skan: found={fr.get('found')} linie={fr.get('lines')}/{fr.get('lines_total')} napisy={fr.get('texts')} ukryty={fr.get('hidden')} obce={fr.get('foreign')} piksele={fr.get('pixels')} err_mm={fr.get('err_mm')}"
    act = None
    if fr.get("found"): act = {"gl": gl, "glpage": 1}
    elif fr.get("foreign"): act = {"gl": gl, "glpage": 1, "foreign": True}
    if act:
        r = T.post_json(f"/api/jobs/{jid}/steps", {"name": "frames", "params": {"page": 0, **act}})
        if "_status" in r: line += f" | usuwanie: BŁĄD {r.get('error')}"
        else:
            v = r["versions"][-1]["id"]; f = f"/home/user/print_checker/app/work/{jid}/{v}.pdf"
            im = look(f)
            m = P.measure(ref, im) if im.size == ref.size or abs(im.width / im.height - ref.width / ref.height) < 0.01 else None
            line += f" | po usunięciu vs czysty: {m}"
            P.triptych(ref, im.resize(ref.size), f"wynik_{name}.jpg")
    print(line, flush=True)
