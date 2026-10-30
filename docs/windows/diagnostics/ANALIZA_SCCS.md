# SCCS.exe: analiza statyczna obsługi suwaka głośności

> Dokument historyczny (v7). Aktualny protokol dotyku AA 06 opisano w README_WINDOWS.md.


Materiał: dostarczone archiwum `SCCS-static.zip`; nie uruchamiano EXE/DLL ani sterownika SCCS.sys.

## Potwierdzone na podstawie instrukcji x64 w SCCS.exe

- Główny program wykorzystuje `ReadFile`, `WriteFile`, `CreateFileW`, `SetCommState` i `GetCommState` — komunikacja szeregowa.
- W `SCCS.exe` znajdują się zarówno teksty `{VOLUME:%d}` (wysyłanie wartości), jak i `{VOLUME SET:%d}` (rejestrowanie żądania zmiany). Ten drugi tekst jest używany przy rozpatrywaniu kodu `0x61`.
- W wątku przetwarzającym przychodzącą ramkę, pod adresem VA `0x14000adf8` odczytywany jest kod z bufora `[0x140023362]`; wartości 0x30..0x3c odpowiadają regularnym żądaniom kafelków. Dodatkowo program rozpoznaje `0x60`, `0x61`, `0x62`.
- Gałąź dla `0x61` (VA `0x14000b006`–`0x14000b114`) pobiera wartość z `[0x140023363]` (czwarty bajt ramki), przelicza ją do skali [0, 1] (dzielenie przez stałą 100), a następnie wywołuje metodę COM audio z offsetem vtable `0x38` (`IAudioEndpointVolume::SetMasterVolumeLevelScalar`, przy standardowej kolejności metod). Zapisuje także tekst `{VOLUME SET:%d}`.
- SCCS wysyła potem 8-bajtowe potwierdzenie `AA 05 00 32 CC 33 C3 3C` (zob. konstrukcję bufora przy `0x14000b097`).
- Odbiornik zbiera dane zaczynając od `AA`; rozpoznaje koniec ramki przez zakończenie `CC 33 C3 3C` (VA `0x14000d480`–`0x14000d4de`).

### Odtworzony pakiet suwaka

```text
AA 05 61 VV CC 33 C3 3C
         │  └── VV = żądany poziom głośności, bajt 0..100
         └───── 0x61 = kod zdarzenia dotykowej regulacji
```

Przykład **hipotetyczny**, zgodny z logiką SCCS (nie przechwycony na urządzeniu):

```text
AA 05 61 32 CC 33 C3 3C    -> 50%
AA 05 00 32 CC 33 C3 3C    <- ACK od hosta
```

### Ograniczenie ważne dla aktualnego problemu

W przesłanym wcześniej logu panelu były **wyłącznie żądania ENQ** `AA 05 <SEQ> CC 33 C3 3C` (586 ramek w analizie), bez bajtu `0x61`. Nie jest zatem potwierdzone, czy aktualne oprogramowanie panelu transmituje zdarzenia dotyku bez dodatkowej inicjalizacji ze strony SCCS. Możliwe wyjaśnienia: brak aktywacji ścieżki dotykowej, inna sekwencja uruchomienia lub nieprzechwycony transport. Samo zaimplementowanie parsera nie gwarantuje, że panel zacznie emitować zdarzenia.

## Windows adapter v7 (wersja testowa)

- Zachowano integracje z v6.1: Windows Audio (Windows → LCD), temperatury CPU (LibreHardwareMonitor), NVMe (natywna Windows API), GPU i pogodę.
- Nowy `atomman_touch_volume.py` **nie otwiera COM3**, a jedynie obserwuje kopię bajtów już odbieranych przez istniejące `serial.Serial.read()`.
- `--touch-monitor` — tryb pasywny: pokazuje poprawne zdarzenia dotykowe, bez zmieniania głośności i bez ACK.
- `--touch-volume` — dla poprawnej ramki `AA 05 61 VV CC 33 C3 3C` ustawia poziom głośności Windows (`pycaw`) i dopiero po powodzeniu wysyła potwierdzenie.
- Niezidentyfikowane dane i standardowe ENQ nie wywołują żadnego zapisu do głośności.
- Na razie nie twierdzimy, że sterowanie suwaka jest naprawione: brakuje potwierdzenia napływu zdarzeń `0x61` od fizycznego urządzenia.

## Instalacja / próby

1. Zatrzymaj dotychczasowy skrypt `Ctrl+C`.
2. Zrób kopię `screen_windows.py` z v6.1.
3. Podmień jedynie `screen_windows.py` i dodaj nowy `atomman_touch_volume.py` (oraz pomocniczy `atomman_nvme_temp_test.py`, jeśli go nie ma). Zachowaj `screen.py` i `screen_windows.local.json`.
4. `py .\screen_windows.py --touch-self-test`
5. `py .\screen_windows.py --port COM3 --start-delay 5 --touch-monitor`; poruszaj suwakiem kilka razy, obserwuj komunikaty `[LCD TOUCH]`.
6. Jeżeli pojawi się `Event 0x61 requests N%`, uruchom `py .\screen_windows.py --port COM3 --start-delay 5 --touch-volume` i sprawdź aktualizację Windows.
7. Jeżeli nie ma żadnych zdarzeń, zatrzymaj i wróć do działającej v6.1. Trzeba zbadać aktywację transmisji zdarzeń. **Nie uruchamiaj SCCS/SCCS.sys na zwykłym hoście tylko dla diagnozy.**

Narzędzie przeszło test składni, dekodera (fragmentacja, dane zwykłe, pakiety 30%, 100%, błędne wartości) i test z zasymulowanym portem (niezmienione dane `read`, ACK, brak skutków na innym COM). **Nie testowano na rzeczywistym panelu.**
