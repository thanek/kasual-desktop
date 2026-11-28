from typing import Protocol


class PointerHiding(Protocol):
    def hide_while_idle(self) -> None: ...
    def keep_visible(self) -> None: ...


class UncontrolledPointer(PointerHiding):
    def hide_while_idle(self) -> None:
        pass

    def keep_visible(self) -> None:
        pass
