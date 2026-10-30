# AtomMan X7 Ti Windows – diagnostyka COM3 i czujników

Plik `atomman_serial_capture.py` umieść obok **działających** `screen_windows.py` i `screen.py`. Nie zastępuje ani nie modyfikuje tych plików.

## Suwak głośności – ustalenie protokołu

1. Zatrzymaj bieżący proces Python (`Ctrl+C`). SCCS musi pozostać wyłączony.
2. W PowerShell:

```powershell
cd $HOME\AtomMan
py .\atomman_serial_capture.py --port COM3 --start-delay 5
```

3. Poczekaj, aż pojawi się `[OK] Screen activated`.
4. Na wyświetlaczu wybierz głośność, przesuń suwak np. do 20%, następnie do 50% i 80%. Jeśli Windows nie reaguje, to jest właśnie przedmiot diagnostyki.
5. Zatrzymaj `Ctrl+C` i prześlij `atomman_touch_rx.log` do analizy. Rejestrowane są **tylko** dane RX, bez wysyłanych metryk, pogody czy klucza API. Rejestrator nie otwiera COM3 samodzielnie; przechwytuje odczyty istniejącego adaptera.

Jeśli RX nie zmieni się podczas dotykania, panel może obsługiwać suwak lokalnie, emitować inny typ zdarzenia albo wymagać osobnego kanału. Nie wolno zgadywać komend do sterowania głośnością.

## Odczyt temperatur SSD – Windows Storage API

Bez instalacji dodatkowych sterowników uruchom:

```powershell
Get-PhysicalDisk | ForEach-Object {
  $disk = $_
  $r = $disk | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue
  [pscustomobject]@{
    Disk = $disk.FriendlyName
    BusType = $disk.BusType
    Temperature = if ($r) { $r.Temperature } else { $null }
    TemperatureMax = if ($r) { $r.TemperatureMax } else { $null }
  }
} | Format-Table -AutoSize
```

`Temperature` może być puste albo niewiarygodne dla danego sterownika. Lista dysków może nie mapować się wprost na `C:`; przed przypisaniem pomiaru do kafelka trzeba sprawdzić mapowanie wolumin–dysk.

## CPU i wentylator – tylko odczyt dostępnych interfejsów

```powershell
Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue |
  Select-Object InstanceName, CurrentTemperature

Get-CimInstance Win32_Fan -ErrorAction SilentlyContinue |
  Select-Object Name, DesiredSpeed
```

`MSAcpi_ThermalZoneTemperature` nie jest gwarantowanym odczytem temperatury CPU; może reprezentować inną strefę ACPI, więc nie należy bez identyfikacji mapować go do `CPU temp`. `Win32_Fan` zwykle nie udostępnia rzeczywistego RPM.

## Zasady

- Bez ponownej instalacji SCCS i WinRing0.
- `GPU temp` już działa przez NVML i nie wymaga poprawek.
- `0°C` i `-1 RPM` to wartości zastępcze, nie pomiary.
- Nie usuwaj SCCS przed konfiguracją i testem autostartu adaptera.
