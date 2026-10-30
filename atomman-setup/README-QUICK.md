# AtomMan X7 Ti — Ubuntu 26.04 / instalacja Linux

To repozytorium zawiera program LCD, obsługę dotykowej regulacji głośności i eksperymentalny sterownik `atomman_ec_fan` 0.2.0 dla rzeczywistego RPM wewnętrznego wentylatora.

## Sprawdzone na sprzęcie

- AtomMan X7 Ti, DMI: `Micro Computer (HK) Tech Limited` / `AtomMan X Series` / `MTBAC`.
- Ubuntu 26.04, kernel `7.0.0-42-generic`, Secure Boot ON, DKMS 3.2.2.
- `sensors` raportuje ~1880–1910 RPM bez obciążenia oraz ~2260–2411 RPM w teście CPU.
- Test obciążenia przerwał się automatycznie po osiągnięciu progu 90°C (ostatnia próbka 91°C).
- Po pełnym restarcie: `atomman.service` aktywna, moduł załadowany, `enable_ec_reads=Y`, `fan1` ~1891 RPM.
- **To prototyp specyficzny dla modelu, a nie certyfikowany sterownik.** Nie uruchamiać na innym sprzęcie.

## Instalacja aplikacji

Przed uruchomieniem upewnij się, że skonfigurowano środowisko z `/etc/atomman.env` (zachowaj sekrety poza repozytorium), dostęp do `Synwit` USB COM, NVIDIA i sesję PipeWire/WirePlumber. Starsze skrypty z katalogu `atomman-setup/` dotyczą przygotowania grafiki oraz Secure Boot.

Uruchom z katalogu repozytorium (skrypt działa także z innego bieżącego katalogu):

```bash
bash atomman-setup/50_app_setup.sh
```

Skrypt kopiuje `screen.py`, `screen_linux_audio.py` i `test_linux_audio.py` do `~/atomman/src/`, instaluje zależności z `atomman-setup/requirements.txt`, a następnie instaluje szablon systemd z podstawieniem lokalnego użytkownika i katalogu domowego.

Instalacja samej aplikacji nie wymaga modułu EC: `screen.py` ma fallback do NVIDIA, jeśli `hwmon` nie udostępnia RPM.

**UWAGA:** Systemd odwołuje się do sesji audio użytkownika (`/run/user/<UID>`). Installer podstawia UID konta, ale jego sesja PipeWire/WirePlumber musi być rzeczywiście dostępna.

## Sterownik EC / DKMS (oddzielny, opcjonalny krok)

Nie jest uruchamiany automatycznie przez instalator aplikacji. **Najpierw** budowa i kontrola podpisu bez odczytów EC:

```bash
bash atomman-setup/55_install_ec_fan.sh --build-only
```

Zainstaluj narzędzia testowe: `sudo apt install stress-ng lm-sensors`.

Następnie, **wyłącznie na właściwym sprzęcie i pod nadzorem** przeprowadź test. Skrypt testowy przerwie obciążenie przy 90°C (próg może zostać przekroczony między pomiarami):

```bash
sudo systemctl stop atomman.service
sudo modprobe -r atomman_ec_fan 2>/dev/null || true
sudo modprobe atomman_ec_fan enable_ec_reads=1
bash drivers/atomman-ec-fan/fan_load_test.sh
sudo modprobe -r atomman_ec_fan
sudo systemctl start atomman.service
```

Powyższe polecenia **nie instalują** jeszcze konfiguracji włączającej odczyty po restarcie. Dopiero po udanym, nadzorowanym teście i potwierdzeniu właściwego RPM:

```bash
bash atomman-setup/55_install_ec_fan.sh --enable
```

Skrypt wymaga jawnego potwierdzenia `TAK`, sprawdza DMI, DKMS, podpis i MOK (jeśli Secure Boot jest aktywny), instaluje konfigurację `enable_ec_reads=1`, ładuje moduł i restartuje usługę LCD. Jeżeli moduł był wcześniej załadowany z odczytami wyłączonymi, nie przeładowuje go automatycznie.

**Nie uruchamiaj eksperymentalnego sterownika na sprzęcie bez testów EC.** Szczegóły i rollback są w `drivers/atomman-ec-fan/README.md`. Na wcześniej przetestowanym AtomManie można przejść bezpośrednio do `--enable`.

## Kontrola działania

```bash
systemctl is-active atomman.service
lsmod | grep atomman_ec_fan
sudo cat /sys/module/atomman_ec_fan/parameters/enable_ec_reads
sensors | grep -A 3 atomman_ec_fan
modinfo -F signer atomman_ec_fan
dkms status
```

Oczekiwane: `active`, moduł załadowany, `Y`, odczyt RPM; po zmianie kernela DKMS powinien automatycznie przebudować i podpisać moduł, ale trzeba to ponownie sprawdzić.

## Gdzie są pliki

- `atomman-setup/systemd/atomman.service` — przenośny szablon z `__USER__`, `__HOME__`, `__UID__` (nie kopia `/etc` specyficzna dla konta).
- `atomman-setup/systemd/atomman-ec-fan.conf` — parametr `enable_ec_reads=1`.
- `drivers/atomman-ec-fan/` — kod źródłowy, DKMS, test obciążenia, instrukcja rollback.
- `screen_linux_audio.py` — wrapper PipeWire / dwukierunkowe sterowanie głośnością.
- `/etc/atomman.env` oraz klucze MOK — **lokalnie, poza Git**.

## Ważne ograniczenia

- Używany odczyt EC jest tylko do RPM, bez ustawiania PWM, ale wykonuje polecenia do EC; nie gwarantuje to bezpieczeństwa na innych wersjach BIOS.
- `--fan-max-rpm 2200` służy jedynie szacowaniu RPM z procentu NVIDIA podczas fallbacku; nie ogranicza obrotów wentylatora EC (zmierzono 2411 RPM).
- Nie publikuj kopii `acpidump`, zwłaszcza tabel `MSDM` z możliwym kluczem Windows, ani prywatnych kluczy Secure Boot.
