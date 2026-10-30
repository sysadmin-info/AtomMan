# AtomMan X7 Ti — Linux LCD dashboard, audio, EC fan RPM & Secure Boot

**English:** [Overview](#english) · **Polski:** [Opis projektu](#polski)

AtomMan is a Linux dashboard daemon for the **Minisforum AtomMan X7 Ti USB LCD**. This repository extends the existing `screen.py` with bidirectional touch/volume support and an optional, model-specific Linux `hwmon` driver for **actual internal fan RPM**. It also provides Ubuntu setup scripts for NVIDIA, DKMS and Secure Boot.

> **Project status (2026-10-30):** LCD, touch volume, EC fan RPM and systemd autostart were verified on an AtomMan X7 Ti running Ubuntu 26.04 with kernel `7.0.0-42-generic` and Secure Boot enabled. The refreshed setup scripts have **not** yet been validated on a clean Ubuntu installation.

---

<a id="english"></a>
## English

### Features and scope

- **`screen.py`** — original Python LCD application (system monitoring and weather).
- **`screen_linux_audio.py`** — Ubuntu wrapper for **LCD ↔ PipeWire/PulseAudio** volume control. It uses the existing serial connection and does not modify `screen.py` on disk.
- **`drivers/atomman-ec-fan/`** — optional **`atomman_ec_fan` v0.2.0** read-only RPM sensor driver with a Linux `hwmon` interface, DKMS configuration and supervised CPU-load test.
- **`atomman-setup/`** — NVIDIA/Secure Boot preparation, application installation, optional EC-driver installation and a portable systemd unit template.

The EC module reports fan speed, **not fan control**. The module's `--fan-max-rpm 2200` application argument is used only to estimate NVIDIA fan RPM when the EC sensor is unavailable; it does not limit the internal fan.

### Verified platform

| Component | Verified configuration |
| --- | --- |
| Computer | AtomMan X7 Ti; DMI vendor `Micro Computer (HK) Tech Limited`, product `AtomMan X Series`, board `MTBAC` |
| Operating system | Ubuntu 26.04, Linux `7.0.0-42-generic` |
| Boot and modules | Secure Boot enabled; EC driver v0.2.0 signed with an enrolled MOK and installed by DKMS |
| Idle EC fan | Approximately 1880–1910 RPM |
| CPU-load test | RPM rose to approximately 2260–2411; the test stopped at the 90°C safety threshold (last sample 91°C) |
| After reboot | `atomman.service` active; module loaded; `enable_ec_reads=Y`; `fan1` about 1891 RPM |

**Hardware warning:** EC access is experimental and specific to this tested hardware/firmware combination. Even a *read* operation issues an EC command and address. Do not enable this driver on a different machine or BIOS without independent validation. This is not an officially supported Minisforum driver.

### Repository layout

```text
AtomMan/
├── README.md
├── README_UBUNTU_AUDIO_EN.md
├── README_UBUNTU_AUDIO_PL.md
├── screen.py
├── screen_linux_audio.py
├── test_linux_audio.py
├── drivers/
│   └── atomman-ec-fan/
│       ├── atomman_ec_fan.c
│       ├── Makefile
│       ├── dkms.conf
│       ├── fan_load_test.sh
│       └── README.md
└── atomman-setup/
    ├── 00_check.sh … 70_verify.sh
    ├── 50_app_setup.sh
    ├── 55_install_ec_fan.sh
    ├── README-QUICK.md
    ├── requirements.txt
    ├── sudoers/
    └── systemd/
        ├── atomman.service
        └── atomman-ec-fan.conf
```

**Full instructions:** [Ubuntu setup guide](atomman-setup/README-QUICK.md) · [Audio/touch adapter (EN)](README_UBUNTU_AUDIO_EN.md) · [Audio/touch adapter (PL)](README_UBUNTU_AUDIO_PL.md) · [EC driver, DKMS and rollback](drivers/atomman-ec-fan/README.md).

### Installation: application first

Clone the repository and prepare **`/etc/atomman.env`** locally. Never commit real API keys or other secrets.

```bash
git clone https://github.com/sysadmin-info/AtomMan.git
cd AtomMan

# Example environment file: edit locally and use your own values.
sudoedit /etc/atomman.env
sudo chmod 600 /etc/atomman.env

# Requires the configured environment, Synwit serial device and desktop audio session.
bash atomman-setup/50_app_setup.sh
```

Example **values** for `/etc/atomman.env` (not a ready-to-run creation command):

```dotenv
ATOMMAN_PORT=/dev/serial/by-id/usb-Synwit_USB_Virtual_COM-if00
ATOMMAN_BAUD=115200
ATOMMAN_OWM_API=YOUR_OPENWEATHER_KEY
ATOMMAN_OWM_LOCATION=City,CC
ATOMMAN_OWM_UNITS=metric
ATOMMAN_OWM_LANG=en
ATOMMAN_WEATHER_REFRESH=600
```

Check the actual device path in `/dev/serial/by-id/`. The setup script creates/updates the application at `~/atomman/` and installs the systemd service. **The Git checkout (`~/AtomMan/`) and the runtime directory (`~/atomman/`) are separate.**

**Do not copy** `atomman-setup/systemd/atomman.service` directly to `/etc/systemd/system/`: it is a template containing `__USER__`, `__HOME__` and `__UID__`, which `50_app_setup.sh` substitutes during installation. The service runs as the desktop user and depends on that user's PipeWire/WirePlumber session. Only one process may own the Synwit serial port at a time.

### Optional: internal fan RPM via EC / DKMS

**Step 1 — build and verify the signed module, without enabling EC reads:**

```bash
bash atomman-setup/55_install_ec_fan.sh --build-only
modinfo -F signer atomman_ec_fan
dkms status
```

**Step 2 — supervised hardware validation:** follow the exact instructions in [the Ubuntu setup guide](atomman-setup/README-QUICK.md). Install `stress-ng` and `lm-sensors`, monitor CPU temperature and fan speed, and stop immediately if anything is abnormal. The stress script uses a 90°C safety threshold, which can be exceeded between samples.

**Step 3 — only after successful verification, explicitly enable persistent EC reads:**

```bash
bash atomman-setup/55_install_ec_fan.sh --enable
```

The installer checks DMI, DKMS and signing/MOK status and asks for `TAK` confirmation. **If the module is already loaded with reads disabled (`N`), the installer will not reload it automatically.** After it has written `/etc/modprobe.d/atomman-ec-fan.conf`, stop `atomman.service`, run `sudo modprobe -r atomman_ec_fan`, and start the service again. With the module enabled, `hwmon` supplies real RPM to `screen.py`; if EC RPM is unavailable, the application can fall back to an NVIDIA-derived estimate. On the tested installation, the systemd command uses `--fan-prefer hwmon --fan-max-rpm 2200`.

### Verify and troubleshoot

```bash
systemctl status atomman.service --no-pager -l
systemctl is-active atomman.service
lsmod | grep atomman_ec_fan
sudo cat /sys/module/atomman_ec_fan/parameters/enable_ec_reads
sensors | grep -A 3 atomman_ec_fan
modinfo -F signer atomman_ec_fan
dkms status
sudo journalctl -u atomman.service -b --no-pager -n 80
sudo tail -n 80 /var/log/atomman.log
```

`enable_ec_reads=Y` and a positive `fan1` reading confirm EC reporting. If the module is intentionally absent, skip the `/sys/module/...` check; the LCD can still run using the NVIDIA fallback. After a kernel upgrade, check DKMS installation **and the module signature** again.

Older numbered scripts (`10_purge_nvidia.sh`, `20_install_nvidia.sh`, `30_secureboot_enroll_key.sh`, `40_sign_or_reinstall_dkms.sh`) may change drivers, enroll keys or **reboot the machine**. Do not run them as part of an ordinary app update. Consult their contents first.

### Security and limitations

Keep `/etc/atomman.env`, MOK private keys/certificates and firmware/ACPI dumps out of Git. A full ACPI dump may contain an `MSDM` table with a Windows activation key. The experimental EC module does not implement PWM or fan-speed control. Review the [driver's rollback section](drivers/atomman-ec-fan/README.md) before persistent installation.

This repository does not yet include the separate Windows adapter as a committed implementation. Verify the license and attribution requirements of the upstream code before redistributing modified versions.

---

<a id="polski"></a>
## Polski

### Funkcje projektu

- **`screen.py`** — główny program obsługujący wyświetlacz LCD (monitoring systemu i pogoda).
- **`screen_linux_audio.py`** — nakładka obsługująca **dwukierunkową regulację głośności LCD ↔ PipeWire/PulseAudio** bez modyfikowania pliku `screen.py` na dysku.
- **`drivers/atomman-ec-fan/`** — opcjonalny sterownik **`atomman_ec_fan` v0.2.0**, który udostępnia rzeczywiste RPM wewnętrznego wentylatora przez Linux `hwmon`, wraz z DKMS i testem obciążeniowym.
- **`atomman-setup/`** — skrypty przygotowania NVIDIA/Secure Boot, instalacji programu i sterownika oraz szablon usługi systemd.

Sterownik EC **odczytuje RPM, ale nie steruje wentylatorem**. Argument `--fan-max-rpm 2200` służy wyłącznie do szacowania RPM wentylatora NVIDIA przy braku danych z EC; nie ogranicza obrotów wentylatora komputera.

### Potwierdzone testy

| Element | Wynik |
| --- | --- |
| Sprzęt | AtomMan X7 Ti; DMI: `Micro Computer (HK) Tech Limited` / `AtomMan X Series` / `MTBAC` |
| System | Ubuntu 26.04, kernel `7.0.0-42-generic` |
| Zabezpieczenia | Secure Boot włączony; sterownik EC podpisany kluczem MOK i zainstalowany przez DKMS |
| Wentylator bez obciążenia | Około 1880–1910 RPM |
| Test CPU | Wzrost do około 2260–2411 RPM; automatyczne przerwanie po przekroczeniu progu 90°C (ostatnia próbka 91°C) |
| Po restarcie | `atomman.service` aktywna, sterownik załadowany, `enable_ec_reads=Y`, `fan1` około 1891 RPM |

**Uwaga sprzętowa:** dostęp do EC jest eksperymentalny i zależny od modelu oraz firmware. Nawet odczyt wymaga przesłania polecenia i adresu do kontrolera EC. **Nie włączaj sterownika na innym komputerze ani wersji BIOS bez niezależnej weryfikacji.** Nie jest to oficjalny sterownik Minisforum.

### Pliki i dokumentacja

Struktura katalogów znajduje się w [angielskiej sekcji „Repository layout”](#repository-layout). Szczegółowe instrukcje:

- [Instalacja Ubuntu — instrukcja PL](atomman-setup/README-QUICK.md)
- [Obsługa audio i dotyku — PL](README_UBUNTU_AUDIO_PL.md)
- [Obsługa audio i dotyku — EN](README_UBUNTU_AUDIO_EN.md)
- [Sterownik EC / DKMS i wycofanie zmian](drivers/atomman-ec-fan/README.md)

### Instalacja aplikacji

Sklonuj repozytorium, utwórz lokalny plik `/etc/atomman.env` i uzupełnij konfigurację pogody oraz portu szeregowego. **Nie publikuj prawdziwych kluczy API.**

```bash
git clone https://github.com/sysadmin-info/AtomMan.git
cd AtomMan
sudoedit /etc/atomman.env
sudo chmod 600 /etc/atomman.env
bash atomman-setup/50_app_setup.sh
```

Przykładowe wartości zmiennych pokazano w [sekcji angielskiej](#installation-application-first). Zweryfikuj właściwą ścieżkę portu Synwit w `/dev/serial/by-id/`.

Instalator umieszcza aplikację w `~/atomman/`, natomiast repozytorium Git może znajdować się w `~/AtomMan/` — **to różne katalogi**. `50_app_setup.sh` instaluje `screen.py`, `screen_linux_audio.py`, `test_linux_audio.py`, zależności oraz usługę systemd. Nie kopiuj ręcznie szablonu `atomman.service` do `/etc`: zawiera znaczniki `__USER__`, `__HOME__`, `__UID__`, które instalator zastępuje lokalnymi wartościami.

Dwukierunkowa regulacja głośności wymaga działającej sesji PipeWire/WirePlumber użytkownika. Nie uruchamiaj jednocześnie dwóch programów korzystających z tego samego portu szeregowego LCD.

### Opcjonalny sterownik EC / DKMS

**1. Budowa modułu bez włączania odczytów EC:**

```bash
bash atomman-setup/55_install_ec_fan.sh --build-only
modinfo -F signer atomman_ec_fan
dkms status
```

**2. Nadzorowany test sprzętowy:** wykonaj kroki z [instrukcji instalacji](atomman-setup/README-QUICK.md). Test wymaga `stress-ng` i `lm-sensors`. Obserwuj temperaturę CPU i RPM; skrypt zatrzymuje obciążenie przy progu 90°C, ale temperatura może chwilowo przekroczyć ten próg między odczytami.

**3. Dopiero po pomyślnym teście włącz odczyty na stałe:**

```bash
bash atomman-setup/55_install_ec_fan.sh --enable
```

Instalator sprawdza DMI, DKMS i podpis/MOK oraz wymaga wpisania `TAK`. **Jeśli moduł był już załadowany z wyłączonymi odczytami (`N`), instalator nie przeładuje go samodzielnie.** Po zapisaniu `/etc/modprobe.d/atomman-ec-fan.conf` zatrzymaj `atomman.service`, wykonaj `sudo modprobe -r atomman_ec_fan` i ponownie uruchom usługę. Moduł udostępnia RPM przez `hwmon`; gdy brak odczytu EC, aplikacja może użyć szacunkowej wartości z NVIDIA. Na przetestowanym komputerze usługa korzysta z argumentów `--fan-prefer hwmon --fan-max-rpm 2200`.

### Kontrola działania i diagnostyka

```bash
systemctl is-active atomman.service
lsmod | grep atomman_ec_fan
sudo cat /sys/module/atomman_ec_fan/parameters/enable_ec_reads
sensors | grep -A 3 atomman_ec_fan
modinfo -F signer atomman_ec_fan
dkms status
sudo journalctl -u atomman.service -b --no-pager -n 80
sudo tail -n 80 /var/log/atomman.log
```

Oczekujemy działającej usługi (`active`), załadowanego modułu, parametru `Y` i dodatniej wartości `fan1`. Jeśli sterownik EC nie jest używany, pomiń odczyt `/sys/module/...`: LCD może nadal działać z danymi NVIDIA. Po aktualizacji kernela sprawdź ponownie DKMS i podpis modułu.

Starsze skrypty NVIDIA/Secure Boot mogą usuwać lub instalować sterowniki, rejestrować klucze i **restartować komputer**. Nie uruchamiaj ich bez przeczytania zawartości; nie są częścią zwykłej aktualizacji programu.

### Bezpieczeństwo i ograniczenia

Plik `/etc/atomman.env`, prywatne klucze MOK oraz zrzuty ACPI pozostają poza repozytorium. Pełny zrzut ACPI może zawierać tabelę `MSDM` z kluczem aktywacyjnym Windows. Sterownik EC nie zmienia ustawień PWM ani obrotów. Przed trwałą instalacją przeczytaj [instrukcję wycofania zmian](drivers/atomman-ec-fan/README.md).

Adapter Windows jest obecnie rozwijany oddzielnie i nie jest częścią zatwierdzonej wersji repozytorium. Przed dalszą dystrybucją kodu zweryfikuj warunki licencji i wymagane informacje o autorach projektu źródłowego.
