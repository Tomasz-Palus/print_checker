"""Klucz do podpisywania aktualizacji adCheckera (przegląd kodu B16) — uruchamia Tomasz, RAZ.

    py packaging\\klucz_aktualizacji.py

Co robi:
  1. losuje nowy klucz (Ed25519) na TWOIM komputerze,
  2. wpisuje klucz PUBLICZNY do app/update_key.py (ten plik idzie na GitHuba — tak ma być),
  3. wypisuje klucz PRYWATNY na ekran — nigdzie go nie zapisuje.

Potem, zanim wypchniesz zmianę:
  • GitHub → repozytorium → Settings → Secrets and variables → Actions → New repository secret,
    nazwa: ADCHECKER_SIGN_KEY, wartość: klucz prywatny z ekranu;
  • zapisz go też w menedżerze haseł. Kto go ma, może podpisać aktualizację — nie wysyłaj go nikomu
    i nie wklejaj do repozytorium ani do czatu.
  • podbij wersję i wypchnij. Od tej wersji program instaluje tylko podpisane aktualizacje.

Zgubiony klucz prywatny = nowy klucz tym skryptem (--nowy) i jedna ręczna reinstalacja programu
u wszystkich (stare wersje nie przyjmą podpisu nowym kluczem).
"""
import base64
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)
import ed25519  # noqa: E402

KEY_FILE = os.path.join(APP, "update_key.py")


def main() -> None:
    src = open(KEY_FILE, encoding="utf-8").read()
    old = re.search(r'PUBLIC_KEY\s*=\s*"([0-9a-fA-F]*)"', src)
    if old and old.group(1) and "--nowy" not in sys.argv:
        print("Program ma już klucz publiczny:", old.group(1))
        print("Nowy klucz tylko świadomie (stare wersje nie przyjmą aktualizacji): dopisz --nowy")
        sys.exit(1)
    seed = os.urandom(32)
    pub = ed25519.public_key(seed).hex()
    msg = b"test"
    assert ed25519.verify(bytes.fromhex(pub), msg, ed25519.sign(seed, msg))
    src = re.sub(r'PUBLIC_KEY\s*=\s*"[0-9a-fA-F]*"', f'PUBLIC_KEY = "{pub}"', src)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(src)
    print("Klucz publiczny wpisany do app/update_key.py:")
    print("   ", pub)
    print()
    print("KLUCZ PRYWATNY — wklej jako sekret ADCHECKER_SIGN_KEY na GitHubie i zapisz w menedżerze haseł:")
    print()
    print("   ", base64.b64encode(seed).decode())
    print()
    print("Nigdzie indziej go nie zapisuj. Najpierw sekret na GitHubie, potem wypchnięcie.")


if __name__ == "__main__":
    main()
