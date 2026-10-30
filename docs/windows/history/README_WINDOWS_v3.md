# AtomMan X7 Ti — Windows 11: adapter v3

Repozytorium Linuksa `screen.py` pozostaje bez zmian. Adapter przejmuje metryki
i komunikację wyświetlacza po COM3.

## Instalacja

1. Skopiuj `screen_windows_v3.py` jako `screen_windows.py` obok oryginalnego `screen.py`.
2. Skopiuj `screen_windows.local.example.json` jako `screen_windows.local.json` do tego samego katalogu.
3. Wpisz swój prywatny klucz OpenWeatherMap w pliku `screen_windows.local.json`.
4. W pliku `.gitignore` dopisz: `screen_windows.local.json` (nie publikuj klucza API).
5. Zatrzymaj SCCS/SCCSLaunch przed otwarciem portu COM3.

Testy (PowerShell):

```powershell
py .\screen_windows.py --audio-test
py .\screen_windows.py --check-api --port COM3
py .\screen_windows.py --port COM3 --start-delay 5
```

Wersja v3 nie instaluje sterowników do odczytu temperatur CPU/SSD ani RPM.
Zera/ujemne wartości w protokole oznaczają brak tych odczytów, nie rzeczywistą temperaturę.
`177` oznacza brak baterii w tym protokole; komputer stacjonarny nie ma baterii.

## Uwagi

- To adapter do lokalnego `screen.py`, a nie zamiennik jego repozytorium.
- `--audio-test` pokaże przyczynę `-1%` bez otwierania portu COM.
- `--dashboard` drukuje dużo danych; przy normalnym działaniu pomiń tę flagę.
- Nie dodawaj wyjątków Defendera dla WinRing0.
