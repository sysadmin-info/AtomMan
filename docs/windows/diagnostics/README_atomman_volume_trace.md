# AtomMan X7 Ti — test głośności w obu kierunkach (Windows 11)

Nie nadpisuj działających `screen_windows.py` ani `screen.py`. SCCS powinien pozostać zatrzymany; aktywna zapora SCCS nie przeszkadza Pythonowi.

## 1. Analiza istniejącego logu (bez otwierania COM3)

Wypakuj `atomman_volume_trace.py` do katalogu `$HOME\AtomMan`, tam gdzie `atomman_touch_rx.log`, i uruchom:

```powershell
cd $HOME\AtomMan
py .\atomman_volume_trace.py --analyze-log .\atomman_touch_rx.log
```

Wynik wypisuje liczbę standardowych ramek ENQ (`AA 05 XX CC 33 C3 3C`) i inne ramki. Zależnie od formatu protokołu ramki dotyku mogą, ale nie muszą, wystąpić jako `OTHER`. Brak OTHER nie dowodzi całkowitego braku komunikacji dotykowej innym kanałem.

## 2. Test odczytu Windows / zapisu na panel / dotyku

Zamknij inne aplikacje korzystające z COM3, zatrzymaj działający `screen_windows.py` przez `Ctrl+C`, następnie:

```powershell
py .\atomman_volume_trace.py --port COM3 --start-delay 5
```

Test:

1. Po `[OK] Screen activated` w Windows ustaw głośność kolejno 30% i 70%. Obserwuj komunikaty `WINDOWS VOLUME=...` i `TX VOLUME=...`. Sprawdź, czy fizyczny ekran odzwierciedla zmiany.
2. Dotknij symbolu głośności na ekranie i przesuń suwak w inne miejsca. Obserwuj `RX OTHER` oraz czy zmienia się `WINDOWS VOLUME=...`.
3. Zatrzymaj `Ctrl+C`.

Wynik testu zapisuje się w `atomman_volume_trace.log`. Załącz go do rozmowy razem z `atomman_touch_rx.log`, jeżeli dostępny. Wpisy RX OTHER zawierają odebrane bajty; przed publiczną publikacją przejrzyj log, choć narzędzie nie zapisuje wysyłanych danych pogodowych, klucza API ani pozostałych metryk.

Wyników nie należy interpretować jako dowodu możliwości sterowania głośnością bez znajomości protokołu dotyku. `RX OTHER` i różnice wartości umożliwią dalszą implementację.
