# AtomMan X7 Ti — Windows v9: naprawa dotykowego suwaka głośności

## Potwierdzone na prawdziwym logu COM3

W przesłanym `atomman_touch_dtr.log` znaleziono dokładnie 3 ramki:

- `AA 06 61 00 CC 33 C3 3C` → 0%
- `AA 06 61 20 CC 33 C3 3C` → 32%
- `AA 06 61 00 CC 33 C3 3C` → 0%

Oprócz tego 127 siedmiobajtowych ramek ENQ `AA 05 XX CC 33 C3 3C`.

**Błąd v8:** parser szukał wyłącznie `AA 05`, przez co pomijał zdarzenia suwaka o nagłówku `AA 06`. Naprawiony `atomman_touch_volume.py` rozpoznaje obydwa formaty. Oryginalnego Linux `screen.py` nie trzeba zmieniać.

## Instalacja

1. Zatrzymaj uruchomiony `screen_windows.py` (`Ctrl+C`). Nie uruchamiaj SCCS ani jego sterownika.
2. W `$env:USERPROFILE\AtomMan` wykonaj kopię **tylko** modułu dotyku:

```powershell
cd $HOME\AtomMan
Copy-Item .\atomman_touch_volume.py .\atomman_touch_volume_v8_backup.py
```

3. Rozpakuj ZIP i **zastąp tylko `atomman_touch_volume.py`**. `screen_windows.py` v8, `atomman_lhm_direct.py`, `screen.py`, `screen_windows.local.json` i DLL zostaw niezmienione. W ZIP znajduje się również pełny adapter v9, ale jego podmiana nie jest wymagana.
4. Użyj PowerShell jako administrator (w tym trybie bezpośredni odczyt CPU już działał):

```powershell
py .\screen_windows.py --touch-self-test
py .\screen_windows.py --port COM3 --start-delay 5 --touch-monitor --touch-sccs-dtr
```

5. Dotknij suwaka LCD. Powinny pojawić się komunikaty:

```text
[LCD TOUCH] Event 0x61 requests 0%
[LCD TOUCH] Event 0x61 requests 32%
```

**Monitor NIE zmienia głośności Windows.** Zatrzymaj przez `Ctrl+C` i przełącz na sterowanie:

```powershell
py .\screen_windows.py --port COM3 --start-delay 5 --touch-volume --touch-sccs-dtr
```

Teraz ramka `AA 06 61 VV CC 33 C3 3C`, `VV` 0–100, ustawia systemowy poziom głośności przez `pycaw` i odsyła SCCS ACK `AA 05 00 32 CC 33 C3 3C` tylko po udanym zapisie.

## Bezpieczeństwo i ograniczenia

- Monitor działa pasywnie; w trybie sterowania wyłącznie prawidłowe ramki suwaka zmieniają głośność. Nie ma modyfikowania BIOS/EC, WinRing0 ani SCCS.
- Komunikacja z LCD nadal używa istniejącego COM3, bez otwierania drugiego portu.
- Parser sprawdzony offline na całym otrzymanym logu (127 ENQ, 3 zdarzenia), testach fragmentacji oraz symulowanym odczycie COM/ACK. **Sterowanie Windows nie było jeszcze sprawdzone na fizycznym urządzeniu po tej poprawce.**
- Temperatura CPU bez aplikacji LibreHardwareMonitor nadal wymaga uprawnień administratora i zainstalowanego PawnIO. Pozostałe funkcje adaptera v8 bez zmian.
- Jeżeli rzeczywisty ekran wysyła zdarzenia tylko z `--touch-sccs-dtr`, używaj tej flagi także w trybie `--touch-volume`.

## Cofnięcie zmiany

```powershell
Copy-Item .\atomman_touch_volume_v8_backup.py .\atomman_touch_volume.py -Force
```
