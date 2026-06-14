Opis buga:
* wywołuję popover menu nad dowolnym kaflem
* nie wybieram żadnej pozycji z menu popovera
* klikam BTN_MODE
* z Home Overlay wybieram "Minimalizuj Pulpit"
* klikam ponownie BTN_MODE i przywracam KD
* widzę ciągle "wiszący" nad kaflem popover z menu
* nie mogę go zamknąć, ani wybrać żadnej z jego pozycji
* przełączając się między kaflami nadal mam nad nimi ten popover

Po poprawce:

Traceback (most recent call last):
  File "/home/xis/projekty/kasual-desktop/src/infrastructure/input/gamepad_watcher.py", line 88, in <lambda>
    lambda: self._btn_mode_emitter.emit(BtnModePressed()))
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/xis/projekty/kasual-desktop/src/domain/shared/event_emitter.py", line 68, in emit
    handler(event)
  File "/home/xis/projekty/kasual-desktop/src/infrastructure/input/gamepad_watcher.py", line 107, in <lambda>
    return self._btn_mode_emitter.subscribe(lambda _evt: handler())
                                                         ^^^^^^^^^
  File "/home/xis/projekty/kasual-desktop/src/application.py", line 87, in _on_btn_mode
    self._desktop.dismiss_overlays()
  File "/home/xis/projekty/kasual-desktop/src/infrastructure/qt/desktop/desktop.py", line 213, in dismiss_overlays
    self._overlays.cancel()
  File "/home/xis/projekty/kasual-desktop/src/domain/shell/open_overlays.py", line 45, in cancel
    self._open.pop().cancel()
    ^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'TilePopoverMenu' object has no attribute 'cancel'

