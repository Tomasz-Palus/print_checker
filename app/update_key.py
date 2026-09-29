"""Klucz publiczny, którym program sprawdza podpis aktualizacji (przegląd kodu B16).

Pusty = aktualizacje sprawdzane jak dotąd, tylko sumą SHA-256 (chroni przed uszkodzeniem pliku,
ale nie przed podmianą przez kogoś, kto przejmie konto GitHuba).

Wpisuje go skrypt packaging/klucz_aktualizacji.py (uruchamia Tomasz — raz, na swoim komputerze).
Od wersji, która ma tu klucz, każda następna musi być podpisana — GitHub pilnuje tego sam
(build.yml przerywa wydanie bez podpisu).
"""
PUBLIC_KEY = ""
