"""adChecker — zainstalowany program (wersja 0.3). To jest plik startowy instalatora.

- Serwer produkcyjny (waitress) w tle, na stałym porcie — pamięć okna (kalibracja monitora,
  ustawienia, samouczek) jest przypisana do adresu, więc port nie może się zmieniać.
- Własne okno programu (pywebview: na Windowsie Edge WebView2, na Macu WebKit). Zamknięcie
  okna kończy program. Gdy okna nie da się otworzyć — zwykła przeglądarka, a program kończy
  się sam kilka minut po zamknięciu karty.
- Drugie uruchomienie nie startuje drugiego serwera (skasowałby pliki robocze pierwszego) —
  otwiera działający program w przeglądarce.
- Dziennik: adchecker.log w folderze użytkownika (paths.LOG).
"""
from __future__ import annotations

import multiprocessing
import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

PORT = int(os.environ.get("ADCHECK_PORT", "47315"))   # 5000 zajmuje na Macu AirPlay
HOST = "127.0.0.1"
IDLE_EXIT_S = 180                                      # tryb przeglądarki: bez karty tyle sekund → koniec


def _log_to_file(paths) -> None:
    if not paths.FROZEN:
        return
    try:
        if os.path.exists(paths.LOG) and os.path.getsize(paths.LOG) > 5_000_000:
            os.replace(paths.LOG, paths.LOG + ".old")
        f = open(paths.LOG, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
    except OSError:
        pass


def _running(url: str) -> bool:
    """Czy pod tym adresem działa już adChecker?"""
    try:
        with urllib.request.urlopen(url + "api/version", timeout=1.5) as r:
            return b'"version"' in r.read()
    except Exception:
        return False


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((HOST, port))
            return True
        except OSError:
            return False


def _serve(app, port: int) -> None:
    from waitress import serve
    serve(app, host=HOST, port=port, threads=16, channel_timeout=600,
          max_request_body_size=1100 * 1024 * 1024, ident="adChecker")


def _selftest(url: str) -> int:
    """ADCHECK_SELFTEST=1 — sprawdzenie zbudowanego programu bez okna (GitHub buduje na maszynach
    bez ekranu): serwer, Ghostscript z paczki, wgranie pliku przykładowego, analiza, zamiana na
    CMYK (profile Ghostscripta) i ocena jakości (procesy liczące — multiprocessing w paczce)."""
    import json
    import uuid
    import gs
    import paths

    def call(path, data=None, method=None, ctype=None):
        req = urllib.request.Request(url + path.lstrip("/"), data=data, method=method)
        if ctype:
            req.add_header("Content-Type", ctype)
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode("utf-8"))

    try:
        print("gs:", gs.exe(), gs.run(["--version"]).stdout.strip() or gs.run(["--version"]).stderr.strip())
        print("wersja:", call("/api/version"))
        sample = os.path.join(paths.STATIC, "samples", "przyklad_adChecker.pdf")
        b = uuid.uuid4().hex
        body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"przyklad_adChecker.pdf\"\r\n"
                f"Content-Type: application/pdf\r\n\r\n").encode() + open(sample, "rb").read() + f"\r\n--{b}--\r\n".encode()
        job = call("/api/upload", body, "POST", f"multipart/form-data; boundary={b}")
        jid, v0 = job["job_id"], job["versions"][0]["id"]
        print("wgrany:", jid, job["file"]["page_count"], "str.")
        a = call(f"/api/jobs/{jid}/analysis?v={v0}&page=0")
        print("analiza: kolory", sorted((a.get("color") or {}).get("families", {})), "fonty", len(a.get("fonts") or []))
        j = call(f"/api/jobs/{jid}/steps", json.dumps({"name": "cmyk", "params": {"page": 0, "profile": "fogra39"}}).encode(),
                 "POST", "application/json")
        print("CMYK:", j["versions"][-1]["step"], j["versions"][-1].get("text", "")[:120])
        for _ in range(600):
            q = call(f"/api/jobs/{jid}/quality?page=0&k=1&block=128&w_mm=1015&h_mm=2014")
            if q.get("status") != "running":
                break
            time.sleep(1)
        print("jakość:", q.get("status"), q.get("verdict"), "obszarów", len(q.get("areas") or []))
        ok = j["versions"][-1]["step"] == "cmyk" and q.get("status") == "done"
    except Exception as e:
        import traceback
        traceback.print_exc()
        ok = False
    print("SELFTEST", "OK" if ok else "BŁĄD")
    return 0 if ok else 1


class Api:
    """Funkcje wołane z okna programu (window.pywebview.api.*)."""

    def save_download(self, jid: str, page: int, name: str) -> dict:
        """„Pobierz plik do druku" w oknie programu: systemowe okno „Zapisz jako"."""
        import webview
        import jobs
        import server
        job = jobs.get(jid)
        if not job:
            return {"ok": False, "error": "Nie ma takiego zadania — wgraj plik jeszcze raz."}
        path, fname, _ = server.download_file(job, int(page), name)
        ext = os.path.splitext(fname)[1].lstrip(".") or "*"
        res = webview.windows[0].create_file_dialog(
            webview.FileDialog.SAVE, save_filename=fname, file_types=(f"Plik do druku (*.{ext})",))
        if not res:
            return {"ok": False}
        dst = res if isinstance(res, str) else res[0]
        if not dst.lower().endswith("." + ext.lower()):
            dst += "." + ext
        shutil.copyfile(path, dst)
        return {"ok": True, "path": dst}


def main() -> None:
    multiprocessing.freeze_support()          # MUSI być pierwsze: procesy liczące jakość (detailmap)
    import paths
    _log_to_file(paths)
    print(f"--- adChecker start {time.strftime('%Y-%m-%d %H:%M:%S')} ---")

    port = PORT
    url = f"http://{HOST}:{port}/"
    if _running(url):
        webbrowser.open(url)
        return
    if not _port_free(port):                  # port zajęty przez coś innego — bierzemy wolny
        with socket.socket() as s:
            s.bind((HOST, 0))
            port = s.getsockname()[1]
        url = f"http://{HOST}:{port}/"

    import jobs
    import products
    import server
    from version import VERSION
    jobs.clean_work_dir()
    st = products.load_products()
    print(f"[adChecker {VERSION}] produkty: {st['count']} ({st['source']}); {url}")
    threading.Thread(target=_serve, args=(server.app, port), daemon=True).start()
    for _ in range(100):
        if _running(url):
            break
        time.sleep(0.1)
    if os.environ.get("ADCHECK_SELFTEST"):
        code = _selftest(url)
        sys.stdout.flush()
        os._exit(code)

    try:
        import webview
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.settings["ALLOW_DOWNLOADS"] = True
        webview.create_window("adChecker", url, width=1440, height=900, min_size=(1000, 640),
                              js_api=Api(), text_select=True)
        gui = "edgechromium" if sys.platform == "win32" else None   # nigdy stary silnik IE
        webview.start(gui=gui, private_mode=False, storage_path=paths.WEBVIEW)
        print("okno zamknięte — koniec")
    except Exception as e:                    # brak WebView2 / WebKit — zwykła przeglądarka
        print(f"okno programu niedostępne ({type(e).__name__}: {e}) — otwieram przeglądarkę")
        server.last_seen["t"] = time.time()
        webbrowser.open(url)
        while time.time() - server.last_seen["t"] < IDLE_EXIT_S:
            time.sleep(5)
        print("nikt nie używa programu — koniec")
    os._exit(0)                               # wątek serwera i procesy liczące kończą się razem z nami


if __name__ == "__main__":
    main()
