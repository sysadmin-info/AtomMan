# AtomMan X7 Ti — Ubuntu, dwukierunkowa głośność v1.2

Adapter jest **dostosowany do screen.py przesłanego w rozmowie 2026-10-26**. Nie zastępuje i nie modyfikuje oryginalnego `screen.py` (CPU/GPU/RAM/SSD/NET/DATE/OWM/ENQ pozostają bez zmian).

## Co dokładnie było niekompatybilne

1. `read_enq()` w `screen.py` akceptuje tylko `AA 05 ...`; panel dotykowy nadaje `AA 06 61 XX CC 33 C3 3C`.
2. `DSRDTR` domyślnie `true`. W działającym Windows 11 odbiór dotyku wymagał DTR stale włączonego, bez DSR-handshake.
3. `p_vol()` i `update_latest_from_payload(VOL)` wykonują `pactl get-sink-volume` i zwracają `-1` przy braku aktywnej sesji PulseAudio/PipeWire. Adapter preferuje `wpctl` i awaryjnie `pactl`, używając sesji zalogowanego użytkownika.

Adapter podsłuchuje `serial.Serial.read()` *z tego samego połączenia*, nie otwiera drugiego portu. Po prawidłowym dotknięciu (0..100%) ustawia wolumen przez `wpctl`/`pactl` i odsyła ACK `AA 05 00 32 CC 33 C3 3C`. Tryb monitorowania tylko loguje, niczego nie ustawia.

## Wymagania

Ubuntu/Linux, Python 3.10+, `pyserial` (`python3 -c 'import serial'`), oraz `wpctl` lub `pactl`. Nie instaluj żadnych nowych sterowników. Uruchamiaj adapter **jako zwykły użytkownik pulpitu**, nie z `sudo` — dla PipeWire `XDG_RUNTIME_DIR` musi wskazywać na sesję użytkownika.

Umieść `screen_linux_audio.py` obok aktualnego `screen.py`. To jedyny plik wykonywany na Ubuntu z tego archiwum.

## Krok 1: test audio (bez LCD)

```bash
cd /sciezka/do/AtomMan
python3 screen_linux_audio.py --self-test
python3 screen_linux_audio.py --audio-test
python3 screen_linux_audio.py --check-volume-tile
```

Spodziewaj się `[LINUX AUDIO] VOL payload: {VOLUME:50}` (liczba przykładowa). Jeśli zamiast tego jest `-1`, sprawdź:

```bash
id -un
printf '%s\n' "$XDG_RUNTIME_DIR"
wpctl get-volume @DEFAULT_AUDIO_SINK@
pactl get-sink-volume @DEFAULT_SINK@
```

Brak sesji audio (typowo usługa systemowa startująca jako root) to osobny problem niż dotyk. W takiej sytuacji testuj najpierw ręcznie jako zwykły użytkownik zalogowanego pulpitu.

## Krok 2: test dotyku (nie zmienia wolumenu)

Zatrzymaj starą usługę `screen.py` / stary proces, by port szeregowy był wolny. Jeśli pyserial nie ma dostępu do portu, użytkownik zwykle musi należeć do grupy `dialout` (wylogowanie/zalogowanie po zmianie grup).

```bash
python3 screen_linux_audio.py --touch-monitor --start-delay 5
```

Dotknij głośności na LCD. Oczekuj np. `[LCD TOUCH] Event 0x61 requests 60%`.

## Krok 3: prawdziwe sterowanie LCD <-> Ubuntu

Zatrzymaj monitor `Ctrl+C`, potem:

```bash
python3 screen_linux_audio.py --touch-volume --start-delay 5
```

Sprawdź zmianę z LCD na Ubuntu:

```bash
wpctl get-volume @DEFAULT_AUDIO_SINK@
```

Sprawdź odwrotnie:

```bash
wpctl set-volume @DEFAULT_AUDIO_SINK@ 25%
wpctl set-volume @DEFAULT_AUDIO_SINK@ 75%
```

Ekran powinien aktualizować suwak podczas kolejnej aktualizacji kafelka VOL; niekoniecznie natychmiast. Dla dotyku oczekuj komunikatów `Linux audio update: OK` i `ACK`.

## Uwaga o usłudze systemd

Jeśli wcześniejszy `screen.py` działa jako `systemd` *system service* pod rootem, może nie mieć dostępu do dźwięku użytkownika. Przy automatyzacji preferuj `systemd --user` uruchamiany po starcie sesji PipeWire/WirePlumber. Nie uruchamiaj starego i nowego procesu na tym samym porcie.

## Diagnostyka

- Błąd portu: `ls -l /dev/serial/by-id/`, `groups`, sprawdź czy stara usługa została zatrzymana.
- Brak wolumenu: wynik `--audio-test`; nie uruchamiaj przez `sudo`.
- Brak dotyku: najpierw `--touch-monitor`. Protokół `AA 06 61` sprawdzono na faktycznym urządzeniu pod Windows.
- Wszystkie zmiany dotyczą tylko głośności, DTR/RTS i opcjonalnego wskazania Volume w dashboardzie. Oryginalny `screen.py` pozostaje nietknięty.

**Status:** testy parsera na oryginalnym logu z 2026-10-25 (127 ENQ, 3 zdarzenia 0/32/0%), testy symulacyjne `wpctl`/`pactl`, kafelka VOL, dashboardu i ACK zaliczone. Działanie na fizycznym Ubuntu wymaga Twojego testu.

## Poprawka v1.2: Python 3.14 i `argparse`

Twoja wersja `screen.py` zawiera `help="... RPM = % * this / 100"`. `argparse` interpretuje pojedyncze `%` jako formatowanie i kończy z `ValueError: badly formed help string` jeszcze przed startem ekranu. v1.2 zamienia wyłącznie w pamięci interpretera `RPM = % * this / 100` na `RPM = %% * this / 100`. Oryginalny plik pozostaje bez zmian. `pactl` nie jest zainstalowany, ale `wpctl` działa i wystarcza.

Uruchom z katalogu z `screen.py`:

```bash
python3 screen_linux_audio.py --self-test
python3 screen_linux_audio.py --touch-monitor --start-delay 5
# po potwierdzeniu ramki 0x61:
python3 screen_linux_audio.py --touch-volume --start-delay 5
```

Przed testem zatrzymaj `sudo systemctl stop atomman.service`. Po zakończeniu testu możesz przywrócić oryginalną usługę poleceniem `sudo systemctl start atomman.service` (jeśli nie chcesz jeszcze zmieniać jej konfiguracji). Nie uruchamiaj dwóch procesów na tym samym porcie.

Uwaga: Twój systemd używa `/home/adrian/atomman/src/screen.py`, a testujesz z `~/AtomMan/screen.py`; są to odrębne ścieżki. Na czas testów nie ruszamy systemd.
