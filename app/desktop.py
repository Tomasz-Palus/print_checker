"""adChecker — zainstalowany program (wersja 0.3, start przebudowany w 0.6.13). To jest plik startowy instalatora.

- Serwer produkcyjny (waitress) w tle, na stałym porcie — pamięć okna (kalibracja monitora,
  ustawienia, samouczek) jest przypisana do adresu, więc port nie może się zmieniać.
- Własne okno programu (pywebview: na Windowsie Edge WebView2, na Macu WebKit). Zamknięcie
  okna kończy program. Gdy okna nie da się otworzyć — zwykła przeglądarka, a program kończy
  się sam kilka minut po zamknięciu karty.
- Drugie uruchomienie nie startuje drugiego serwera (skasowałby pliki robocze pierwszego) —
  otwiera działający program w przeglądarce. Rozstrzyga blokada pliku (instance.py).
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

    def save_download(self, jid: str, page: int, name: str, v: str | None = None,
                      w_mm: float | None = None, h_mm: float | None = None) -> dict:
        """„Pobierz plik do druku" w oknie programu: systemowe okno „Zapisz jako".
        `v` — zaakceptowana wersja (inna niż ostatnia = odmowa, przegląd 09.10, A9);
        `w_mm`/`h_mm` — wymiar wydruku, z niego DPI obrazu bez DPI (B18)."""
        import webview
        import jobs
        import server
        job = jobs.get(jid)
        if not job:
            return {"ok": False, "error": "Nie ma takiego zadania — wgraj plik jeszcze raz."}
        if not 0 <= int(page) < job.info["page_count"]:
            return {"ok": False, "error": "Nie ma takiej strony."}
        if v and v != job.head.id:
            return {"ok": False, "error": "Plik zmienił się od chwili akceptacji — sprawdź go jeszcze raz przed pobraniem."}
        pm = None
        try:
            if w_mm and h_mm and 0 < float(w_mm) < 1e6 and 0 < float(h_mm) < 1e6:
                pm = (float(w_mm), float(h_mm))
        except (TypeError, ValueError):
            pm = None
        path, fname, _ = server.download_file(job, int(page), name, pm)
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


def _mac_certs() -> None:
    """Mac: paczka PyInstallera nie widzi systemowych certyfikatów HTTPS — każde pobranie
    (lista produktów, wytyczne, fonty, aktualizacje) kończyło się błędem SSL. SSL_CERT_FILE
    ustawione przed pierwszym połączeniem działa dla całego programu (0.6.13)."""
    if sys.platform != "darwin" or os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except Exception as e:
        print(f"certifi niedostępne: {type(e).__name__}: {e}")


def _stage(msg: str) -> None:
    """Etapy startu w dzienniku z czasem — gdy program stanie, widać, na czym (0.6.13)."""
    print(f"[start {time.strftime('%H:%M:%S')}] {msg}", flush=True)


LOADING_HTML = """<!doctype html><html lang="pl"><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font:15px -apple-system,'Segoe UI',sans-serif;background:#f4f4f2;color:#333}
@media (prefers-color-scheme:dark){body{background:#1e1e1e;color:#ddd}}
.s{width:22px;height:22px;border:3px solid #bbb;border-top-color:#2a8;border-radius:50%;
animation:r 1s linear infinite;margin:0 auto 14px}@keyframes r{to{transform:rotate(360deg)}}
p{text-align:center;max-width:460px;line-height:1.5}</style></head>
<body><div><div class="s"></div><p id="t">Uruchamiam adChecker…</p></div></body></html>"""

WINDOW_WATCHDOG_S = 20     # okno programu nie pokazało się w tym czasie → przeglądarka
SERVER_WAIT_S = 120        # serwer nie wstał w tym czasie → komunikat w oknie


def _start_backend(port: int, url: str, ready: threading.Event, failed: dict) -> None:
    """Wszystko, co może potrwać albo stanąć (import bibliotek PDF, sprzątanie work/, lista
    produktów z sieci, serwer) — w tle, żeby okno pokazało się od razu (0.6.13; dawniej okno
    czekało na to wszystko i na Macu ikona skakała w Docku bez końca)."""
    try:
        import paths
        _stage("import modułów")
        import jobs
        import products
        import server
        from version import VERSION
        import instance
        instance.save_port(port)
        _stage("sprzątanie plików roboczych")
        jobs.clean_work_dir()
        shutil.rmtree(os.path.join(paths.USER_DIR, "update"), ignore_errors=True)   # instalator po aktualizacji
        _stage("serwer")
        threading.Thread(target=_serve, args=(server.app, port), daemon=True).start()
        for _ in range(100):
            if _running(url):
                break
            time.sleep(0.1)
        _stage(f"adChecker {VERSION} gotowy: {url}")
        ready.set()
        # lista produktów (sieć, do 15 s) już po starcie — program ma zapasową listę z paczki
        st = products.load_products()
        _stage(f"produkty: {st['count']} ({st['source']}){' — ' + st['error'] if st.get('error') else ''}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        failed["error"] = f"{type(e).__name__}: {e}"
        ready.set()


def _browser_mode(url: str) -> None:
    """Okna programu nie ma — zwykła przeglądarka; koniec kilka minut po zamknięciu karty."""
    import server
    server.last_seen["t"] = time.time()
    webbrowser.open(url)
    while time.time() - server.last_seen["t"] < IDLE_EXIT_S:
        time.sleep(5)
    print("nikt nie używa programu — koniec")
    _shutdown()
    os._exit(0)


def main() -> None:
    multiprocessing.freeze_support()          # MUSI być pierwsze: procesy liczące jakość (detailmap)
    import paths
    _log_to_file(paths)
    print(f"--- adChecker start {time.strftime('%Y-%m-%d %H:%M:%S')} ({sys.platform}) ---", flush=True)
    _mac_certs()

    port = PORT
    url = f"http://{HOST}:{port}/"
    # jeden program naraz — rozstrzyga blokada pliku, nie odpowiedź serwera (C19): zajęty albo
    # powolny pierwszy program nie może skończyć się skasowaniem jego plików roboczych
    import instance
    if not instance.acquire():
        other = f"http://{HOST}:{instance.running_port(PORT)}/"
        print(f"adChecker już działa ({other}) — otwieram go, nic nie czyszczę")
        webbrowser.open(other)
        return
    if not _port_free(port):                  # port zajęty przez coś innego — bierzemy wolny
        with socket.socket() as s:
            s.bind((HOST, 0))
            port = s.getsockname()[1]
        url = f"http://{HOST}:{port}/"

    ready, failed = threading.Event(), {}
    threading.Thread(target=_start_backend, args=(port, url, ready, failed), daemon=True).start()

    if os.environ.get("ADCHECK_SELFTEST"):
        ready.wait(SERVER_WAIT_S)
        code = 1 if failed or not _running(url) else _selftest(url)
        sys.stdout.flush()
        os._exit(code)

    shown = threading.Event()

    def watchdog() -> None:
        # okno nie pokazało się (WebKit/WebView2 stanął, import pywebview wisi) → przeglądarka,
        # zamiast ikony skaczącej w Docku bez końca (0.6.13)
        if shown.wait(WINDOW_WATCHDOG_S):
            return
        print(f"okno programu nie pokazało się w {WINDOW_WATCHDOG_S} s — otwieram przeglądarkę", flush=True)
        ready.wait(SERVER_WAIT_S)
        _browser_mode(url)

    threading.Thread(target=watchdog, daemon=True).start()

    def load_app(window) -> None:
        # wołane przez pywebview w osobnym wątku, gdy okno już działa
        if not ready.wait(SERVER_WAIT_S) or failed or not _running(url):
            why = failed.get("error", "serwer programu nie odpowiada")
            _stage(f"start nieudany: {why}")
            msg = ("adChecker nie wystartował (" + why + "). Zamknij okno i uruchom program jeszcze raz. "
                   "Szczegóły: dziennik adchecker.log w folderze programu.")
            try:
                window.evaluate_js("document.getElementById('t').textContent=" + json_str(msg))
            except Exception:
                pass
            return
        window.load_url(url)

    try:
        _stage("okno programu")
        import webview
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        webview.settings["ALLOW_DOWNLOADS"] = True
        window = webview.create_window("adChecker", html=LOADING_HTML, width=1440, height=900,
                                       min_size=(1000, 640), js_api=Api(), text_select=True)

        def on_shown(*_):
            if not shown.is_set():
                shown.set()
                _stage("okno widoczne")

        window.events.shown += on_shown
        window.events.loaded += on_shown
        gui = "edgechromium" if sys.platform == "win32" else None   # nigdy stary silnik IE
        webview.start(load_app, window, gui=gui, private_mode=False, storage_path=paths.WEBVIEW)
        print("okno zamknięte — koniec")
    except Exception as e:                    # brak WebView2 / WebKit — zwykła przeglądarka
        print(f"okno programu niedostępne ({type(e).__name__}: {e}) — otwieram przeglądarkę")
        shown.set()                           # strażnik nie otwiera drugiej karty
        ready.wait(SERVER_WAIT_S)
        _browser_mode(url)
    _shutdown()
    os._exit(0)                               # wątek serwera i procesy liczące kończą się razem z nami


def json_str(s: str) -> str:
    import json
    return json.dumps(s)


def _shutdown() -> None:
    """Przed os._exit: Ghostscript i procesy oceny jakości nie mogą liczyć dalej bez okna
    (przegląd kodu 27.09, C20). Wspólne z „Zaktualizuj teraz” — instance.shutdown."""
    import instance
    instance.shutdown()


if __name__ == "__main__":
    main()
