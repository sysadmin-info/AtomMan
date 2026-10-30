# Minisforum AtomMan X7 Ti — Windows 11

Adapter `screen_windows.py` przenosi metryki Windows do istniejącego protokołu LCD z `screen.py`. Konfiguracja dotyczy fizycznego panelu COM3 w testowanym AtomMan X7 Ti. Dokument opisuje stan projektu na **30 października 2026 r.** i nie zastępuje instrukcji bezpieczeństwa Windows.

## Status funkcji

| Funkcja | Źródło | Uwagi |
|---|---|---|
| Wyświetlacz LCD | `screen.py` + `screen_windows.py` / pyserial | Jeden proces używa COM3; nie uruchamiaj jednocześnie SCCS |
| CPU, pamięć, sieć, dysk | `psutil`, Windows API | Systemowe metryki bez SCCS |
| GPU | NVML / `nvidia-smi` | Odczyt temperatury i wykorzystania GPU |
| Temperatura CPU | `atomman_lhm_direct.py` + LibreHardwareMonitorLib.dll **lub** lokalny LHM HTTP | `lhm_dll` aktywuje tryb bezpośredni, a brak `lhm_dll` wybiera lokalny LHM HTTP |
| Temperatura NVMe | `atomman_nvme_temp_test.py` | Windows IOCTL; `disk_number` wybiera fizyczny dysk |
| Głośność Windows → LCD | `pycaw` | COM musi zostać zainicjalizowany w wątku odczytującym |
| Dotykowy suwak LCD → Windows | `atomman_touch_volume.py` | Ramki `AA 06 61 VV CC 33 C3 3C` potwierdzone we wcześniejszym logu; moduł istnieje i jest śledzony przez Git, ale bieżącego działania sprzętu nie testowano w ramach audytu |
| RPM wentylatora CPU | `atomman_aida64_fan.py` | Czyta rejestrowy eksport AIDA64 `Value.FCPU`, wymaga uruchomionego AIDA64 w odpowiednim profilu |
| Natywny RPM EC bez AIDA64 | eksperymentalny `AtomManEC.p` / PawnIO (tylko `feat/windows-adapter`) | **NIEURUCHAMIANY** na Windows — oczekuje na rozwiązanie kwestii ACPI i podpisu; [Issue #134](https://github.com/namazso/PawnIO.Modules/issues/134) |
| Pogoda | OpenWeatherMap | Opcjonalny prywatny klucz; bez klucza brak danych pogodowych |

## Wymagane pliki

W katalogu projektu: `screen.py`, `screen_windows.py`, `atomman_aida64_fan.py`, `atomman_touch_volume.py`, `atomman_lhm_direct.py`, `atomman_nvme_temp_test.py` (zgodnie z włączonymi funkcjami). Lokalnie potwierdzono istnienie i śledzenie przez Git trzech modułów: `atomman_touch_volume.py`, `atomman_lhm_direct.py` i `atomman_nvme_temp_test.py`. Ich działanie na fizycznym sprzęcie nie było sprawdzane w ramach audytu.

Prywatny `screen_windows.local.json` nie powinien trafić do Git. Konfiguracja przykładowa (bez prawdziwego klucza):

```json
{
  "location": "Lodz,PL",
  "owm_api_key": "",
  "disk_number": 0,
  "lhm_dll": "C:\\Tools\\LibreHardwareMonitor\\LibreHardwareMonitorLib.dll"
}
```

Ustaw rzeczywistą ścieżkę `lhm_dll` albo usuń ten klucz, aby użyć wariantu LHM HTTP na `127.0.0.1:8085` (jeśli serwer LHM jest dostępny). `screen_windows.py` korzysta też ze zmiennych środowiskowych `ATOMMAN_PORT`, `ATOMMAN_LOCATION` i `ATOMMAN_OWM_API`.

## Diagnostyka bez otwierania COM3

Uruchamiaj w natywnym PowerShell (nie w WSL), z katalogu projektu:

```powershell
py .\screen_windows.py --list-ports
py .\screen_windows.py --audio-test-background
py .\screen_windows.py --nvme-test
py .\screen_windows.py --touch-self-test
py .\screen_windows.py --cpu-direct-test   # tylko gdy lhm_dll jest skonfigurowany
py .\screen_windows.py --check-api --port COM3
```

`--check-api` nie otwiera COM3, ale odpytuje czujniki/metryki. `--cpu-direct-test` może wymagać uprawnień i wspieranego sterownika dostępu sprzętowego.

## Uruchomienie ekranu

Zatrzymaj SCCS i wszystkie inne programy używające COM3, a następnie:

```powershell
py .\screen_windows.py --port COM3 --start-delay 5
```

Jeżeli trzeba diagnozować dotyk, zacznij od trybu, który **nie** zmienia głośności:

```powershell
py .\screen_windows.py --port COM3 --start-delay 5 --touch-monitor --touch-sccs-dtr
```

Tryb `--touch-volume --touch-sccs-dtr` aktywuje ustawianie głośności Windows oraz ACK i powinien być włączany tylko po potwierdzeniu poprawnego odbioru ramek w trybie monitorowania. Nie uruchamiaj dwóch instancji równocześnie.

## Granice i bezpieczeństwo

- Nie uruchamiaj SCCS.exe ani SCCS.sys w celu diagnostyki i nie obchodź Secure Boot/VBS/HVCI.
- `AtomManEC.amx` jest niepodpisanym artefaktem kompilacji, a nie zatwierdzonym rozwiązaniem do odczytu EC w Windows. Nie uruchamiaj `--read-once`.
- AIDA64 pozostaje dostawcą RPM do czasu uzyskania bezpiecznego, podpisanego modułu lub innego zweryfikowanego rozwiązania.
- Brak odczytu oznaczany przez `0` albo `-1` nie jest prawdziwą temperaturą/obrotami; zależy od pola protokołu.
- Nie publikuj `screen_windows.local.json`, logów COM ani rejestrowych eksportów sensorów bez przejrzenia zawartości.
- Historyczne opisy implementacji v3–v9 przechowuj osobno w `docs/windows/history/`, bez mieszania ich z aktualną instrukcją.

## Narzedzia diagnostyczne i testy offline

Testy uruchamiaj z katalogu glownego AtomMan:

py -B .\tests\windows\smoke_v8.py
py -B .\tests\windows\smoke_v9.py

Diagnostyka:

py -B .\tools\windows\atomman_serial_capture.py --help
py -B .\tools\windows\atomman_volume_trace.py --help

Testy smoke nie otwieraja fizycznego COM3.
Aktywne narzedzia diagnostyczne moga korzystac z COM3.
Logi zapisywane sa w katalogu logs/.
