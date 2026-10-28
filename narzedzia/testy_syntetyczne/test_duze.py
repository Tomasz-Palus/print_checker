"""Analiza bardzo dużych plików z gen_duze.py: czy jest pełna, czy widzi błąd z końca treści, czas
i pamięć. Bez serwera — wprost przez analyze.py.

    python test_duze.py [folder z plikami]
"""
import os
import resource
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(os.path.dirname(HERE)), "app")
DIR = sys.argv[1] if len(sys.argv) > 1 else "pliki_duze"

if len(sys.argv) > 2 and sys.argv[2] == "--jeden":       # podproces: jeden plik (osobny pomiar pamięci)
    sys.path.insert(0, APP)
    import analyze
    t = time.time()
    a = analyze.analyze(sys.argv[3], 0)
    fam = (a["color"]["families"] or {})
    print(round(time.time() - t, 1), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024, a["partial"],
          "RGB" in fam, a["overprint_uses"], ",".join(f["name"] for f in a["fonts"] if not f["embedded"]),
          sum(len(r["placements"]) for r in a["_images"]))
    sys.exit()

# plik → (oczekiwane umiejscowienia obrazu)
CASES = {"D1_symbol_30000x.pdf": 0, "D2_zagniezdzone_100x100.pdf": 0, "D3_plaski_8mln.pdf": 0,
         "D4_symbol_z_obrazem_20000x.pdf": 20000}
ok = 0
for f, places in CASES.items():
    out = subprocess.run([sys.executable, __file__, DIR, "--jeden", os.path.join(DIR, f)], capture_output=True, text=True)
    try:
        t, mb, partial, rgb, op, fonts, n = out.stdout.split()
    except ValueError:
        print(f"BŁĄD  {f}: {out.stderr[-300:]}")
        continue
    good = partial == "False" and rgb == "True" and int(op) >= 1 and "BrakujacyFont" in fonts and int(n) == places
    ok += good
    print(f"{'OK   ' if good else 'BŁĄD '} {f:34s} {t:>6} s {mb:>6} MB  pełna={partial == 'False'} RGB={rgb} "
          f"overprint={op} brak fontu={fonts or '-'} miejsca obrazu={n}")
print(f"\n{ok}/{len(CASES)} OK")
