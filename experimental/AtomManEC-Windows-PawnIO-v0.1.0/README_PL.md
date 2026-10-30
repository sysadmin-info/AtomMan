# AtomMan X7 Ti / Windows / PawnIO — eksperyment v0.1

Stan: **źródła przygotowane, NIE skompilowane ani nieprzetestowane na prawdziwym EC Windows**. Nie zawiera oficjalnie podpisanego `AtomManEC.bin`. Nie zastępuje jeszcze działającego `AIDA64 -> rejestr -> LCD`.

## Zawartość

- `AtomManEC.p`: pojedyncza operacja PawnIO `ioctl_read_fan_rpm`, która wykonuje dwa odczyty vendor EC (`D5 18` i `D5 19`), zwraca `high << 8 | low` i odrzuca wartości >=4000 RPM. Ograniczone odpytywanie statusu, bez arbitralnych adresów czy komend użytkownika.
- `atomman_ec_windows.py`: interfejs `ctypes` do PawnIOLib, kontrola DMI, kontrola czy AIDA64 działa, domyślnie **brak sprzętowego I/O**. `--probe` jedynie sprawdza DMI/ścieżki.
- `build-module.ps1`: lokalne kompilowanie źródła do *niepodpisanego* `.amx` (wymaga `pawncc.exe` i `PawnIO.Modules/include`).
- `tests/test_static.py`: statyczne kontrole krytycznych stałych i modułu Python.

## Od razu po rozpakowaniu — bezpieczna kontrola

W PowerShell z katalogu plików:

```powershell
py -m py_compile .\atomman_ec_windows.py
py .\atomman_ec_windows.py --probe
```

Oczekiwane: DMI, lokalizacja zainstalowanego PawnIO, informacja o **braku podpisanego modułu** (o ile rzeczywiście go nie ma). `--probe` nie wysyła komend do EC ani COM3.

## Kompilacja (opcjonalnie, gdy masz Pawn compiler)

```powershell
git clone https://github.com/namazso/PawnIO.Modules.git C:\Tools\PawnIO.Modules
.\build-module.ps1 -ModulesRepository C:\Tools\PawnIO.Modules -PawnCompiler C:\sciezka\pawncc.exe
```

Powstaje `AtomManEC.amx`. **Nie próbuj ładować go do oficjalnego PawnIO — weryfikacja podpisu go odrzuci.** Należy przygotować PR do PawnIO.Modules, przejść code review i uzyskać opublikowany, podpisany `AtomManEC.bin` z oficjalnego wydania. Wtedy należy zweryfikować pochodzenie binarium i dopiero po zamknięciu AIDA64 użyć:

```powershell
py .\atomman_ec_windows.py --read-once
```

**Nie uruchamiaj `--read-once` dopóki nie masz podpisanej, przejrzanej wersji.** Powyższa komenda ma aktualnie status planowanego testu; nie został wykonany sprzętowo.

## Bezpieczeństwo i ograniczenia

- Ekran AtomMan i działający autostart Windows (`feat/windows-adapter`, commit `21a2565`) pozostają nietknięte.
- Na X7 Ti Linux wywołuje **metodę ACPI** `\\_SB.PC00.LPCB.H_EC.EC2R` (D5, 0x18/0x19), natomiast ten moduł PawnIO wykonuje bezpośrednie I/O. **Równoważność i brak konfliktu z Windows ACPI nie są dowiedzione** — w tym ryzyko wyścigu o EC. To wymaga przeglądu przed testem na sprzęcie.
- „Read-only” oznacza operację odczytu rejestrów EC; na szynie wymagane są zapisy polecenia D5 i adresów do portów 0x6C/0x68.
- Nie testuj równolegle z AIDA64, SCCS czy innymi programami odczytującymi EC; kontrola procesu AIDA64 jest dodatkowym zabezpieczeniem, nie gwarantuje braku kolizji z firmware.
- Nie wyłączaj Secure Boot/VBS/HVCI; nie używaj test-signing ani niepodpisanych sterowników.
- DMI jest sprawdzane w Pythonie, **nie wewnątrz Pawn**; to ograniczenie do omówienia w code review (wymogi upstream).
- Dostęp przez `PawnIO` wymaga odpowiedniego uprawnienia użytkownika i zgodnego, podpisanego modułu.
- `STATUS_IO_TIMEOUT` oznacza brak odpowiedzi EC, a nie zero RPM.

## Referencje

- https://github.com/namazso/PawnIO.Modules/blob/main/LpcACPIEC.p
- https://github.com/namazso/PawnIO.Modules/wiki/Getting-started-with-PawnIO
- https://github.com/namazso/PawnIO.Modules/wiki/Contribution-guidelines
- https://github.com/Gitii/ms-a1-fan-controller
- https://github.com/sysadmin-info/AtomMan/tree/main/drivers/atomman-ec-fan
