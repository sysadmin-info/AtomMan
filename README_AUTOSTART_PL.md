# AtomMan LCD — autostart dla sprawdzonej wersji Windows v9

To archiwum zawiera TYLKO dwa dodatkowe pliki:

- `atomman_background.py`: uruchamia istniejący `screen_windows.py` w tle przez `pythonw.exe`, kieruje stdout/stderr do pliku `logs/atomman.log` (rotacja po 3 MB), czeka 10 s na zalogowanie Windows, a następnie uruchamia adapter z argumentami `--port COM3 --start-delay 5 --touch-volume --touch-sccs-dtr`.
- `install_autostart.ps1`: rejestruje zadanie w Harmonogramie zadań: `AtomMan LCD Python`, podczas logowania bieżącego użytkownika, z uprawnieniami administratora i w sesji interaktywnej (Windows Audio). Nie uruchamia zadania automatycznie przy instalacji, żeby nie zablokować już otwartego COM3.

**Nie zastępuj `screen.py`, `screen_windows.py`, `atomman_touch_volume.py`, `atomman_lhm_direct.py` ani prywatnego JSON.**

## Instalacja

1. Rozpakuj te dwa pliki do `C:\Users\adrian\AtomMan`.
2. Zatrzymaj stary skrypt, jeśli działa. Zalecane jest osobne okno PowerShell jako administrator zalogowanego użytkownika:

```powershell
cd $HOME\AtomMan
Set-ExecutionPolicy -Scope Process Bypass -Force
.\install_autostart.ps1
```

3. Uruchom zadanie bez ponownego logowania:

```powershell
Start-ScheduledTask -TaskName 'AtomMan LCD Python'
Start-Sleep -Seconds 20
Get-ScheduledTask -TaskName 'AtomMan LCD Python' | Select-Object TaskName,State
Get-Content .\logs\atomman.log -Tail 35
```

4. Przesuń suwak LCD i sprawdź regulację Windows. Następnie zmień głośność z Windows i sprawdź suwak LCD. Log zdarzeń:

```powershell
Get-Content .\logs\atomman.log -Wait -Tail 20
```

## Zatrzymanie / cofnięcie

```powershell
Stop-ScheduledTask -TaskName 'AtomMan LCD Python'
Disable-ScheduledTask -TaskName 'AtomMan LCD Python'
# Całkowite usunięcie wpisu z Harmonogramu:
Unregister-ScheduledTask -TaskName 'AtomMan LCD Python' -Confirm:$false
```

## Uwaga o Ctrl+C

Jeśli zaznaczasz tekst myszą w starym oknie Windows PowerShell, tryb QuickEdit potrafi zatrzymać proces. `Ctrl+C` może wtedy kończyć zaznaczanie, a nie służyć do aktywacji portu. Wersja `pythonw.exe` nie otwiera konsoli; wszystkie wpisy trafiają do pliku.

## Ograniczenia

- Uruchamianie całego adaptera jako administrator jest obecnie potrzebne do odczytu CPU przez PawnIO, ale nie jest optymalnym końcowym modelem uprawnień. Później warto wydzielić odczyt CPU do osobnego komponentu.
- Tryb wydajności sprzętu i RPM wentylatora AtomMana pozostają niezaimplementowane.
- Zadanie uruchamia się po *zalogowaniu* użytkownika, nie przed ekranem logowania; to celowe, by sterowanie głośnością działało w jego sesji audio.
- Nie uruchamiaj równolegle `screen_windows.py` i zadania — port COM3 obsługuje tylko jeden proces.
- W razie błędów sprawdź `logs/atomman.log` oraz `Get-ScheduledTaskInfo -TaskName 'AtomMan LCD Python'`.
