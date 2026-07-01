#!/usr/bin/env python3
"""Spike — UX v2.1 / Faza 5, Etap 0 (PoC, bramka).

Weryfikuje warunek techniczny trwałej powierzchni Home (UX.md §8, ux_plan.md
Faza 5): czy collapse↔expand da się zrobić **morphem na jednej, stale
zmapowanej powierzchni layer-shell** — bez map/unmap — tak, by KWin nie wtrącał
własnej animacji okna (problem, przez który Home Overlay tworzony per-press
„miga"). Drugorzędnie: czy zwinięty nagłówek udźwignie rolę top bara (zegar,
data, sieć, badge powiadomień) bez regresji.

Co robi spike
-------------
Tworzy **jedną** powierzchnię wlr-layer-shell (warstwa OVERLAY, kotwica
TOP|LEFT|RIGHT) o **stałej** wysokości (= stan rozwinięty). Powierzchnia
powstaje raz przy show() i nigdy nie jest hide()/destroy(). Morph to wyłącznie
wewnętrzna animacja widżetu *content* (maximumHeight 0↔H + opacity 0↔1) pod
niezmiennym nagłówkiem. Top-level QWindow ma stałą geometrię → KWin nie ma
czego animować.

Tryby (do porównania — to jest sedno bramki):
  * domyślny — morph wewnętrzny (powierzchnia stała). Oczekiwanie: płynnie,
    bez animacji KWin.
  * SPIKE_RESIZE=1 — kontrprzykład: zmieniamy setFixedHeight **samej
    powierzchni** (jak naiwny collapse). Pokazuje, czy resize layer-surface
    prowokuje skok/animację kompozytora.

Auto-cykl co 2.5 s przełącza collapsed↔expanded (obserwacja bez udziału rąk).
Spacja — ręczny toggle, Esc — wyjście, auto-zamknięcie po 90 s (anti-lockout).

Obiektywna weryfikacja (że to wciąż JEDNA powierzchnia):
    WAYLAND_DEBUG=1 python tools/spike_home_surface.py 2>&1 \
        | grep -E 'get_layer_surface|layer_surface@.*destroy'
Dokładnie jeden `get_layer_surface` i ZERO `destroy` przez cały cykl =
powierzchnia trwała (morph, nie remap).

Parytet Windows (NA PAPIERZE — nie testowane w tym środowisku Wayland/KDE)
-------------------------------------------------------------------------
Windows nie ma layer-shell. Odpowiednik: jeden top-level z WS_EX_TOPMOST
(jak promote_overlay_surface dla "windows"), zakotwiczony do górnej krawędzi
ekranu o **stałej** geometrii = stan rozwinięty; ten sam wewnętrzny morph
content (maximumHeight + opacity). DWM nie animuje, bo okno nie zmienia
rozmiaru ani nie jest map/unmap. Klucz przenośności: trzymać powierzchnię
stałą, morphować wnętrze — identycznie jak tu. Tryb SPIKE_RESIZE odradzany na
obu platformach.
"""

import ctypes
import os
import sys

# MUST be set before the Wayland platform plugin initializes.
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
os.environ["QT_WAYLAND_SHELL_INTEGRATION"] = "layer-shell"

# qtawesome is imported lazily in main(), AFTER QApplication exists. Importing
# it earlier registers its sip types before Qt's, breaking QIcon.pixmap(QSize).
qta = None
from PyQt6 import sip
from PyQt6.QtCore import (
    Qt, QTimer, QDateTime, QLocale, QPropertyAnimation, QParallelAnimationGroup,
    QEasingCurve, QSize,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QGraphicsOpacityEffect,
)

# LayerShellQt::Window enum values (mirror the wlr-layer-shell protocol).
LAYER_OVERLAY = 3
ANCHOR_TOP, ANCHOR_LEFT, ANCHOR_RIGHT = 1, 4, 8
ANCHOR_HEADER = ANCHOR_TOP | ANCHOR_LEFT | ANCHOR_RIGHT
KBD_ON_DEMAND = 2   # KD-view context: no fullscreen app under us → safe to focus

_LIB = "libLayerShellQtInterface.so.6"
_SYM_GET   = "_ZN12LayerShellQt6Window3getEP7QWindow"
_SYM_LAYER = "_ZN12LayerShellQt6Window8setLayerENS0_5LayerE"
_SYM_ANCH  = "_ZN12LayerShellQt6Window10setAnchorsE6QFlagsINS0_6AnchorEE"
_SYM_EXCL  = "_ZN12LayerShellQt6Window16setExclusiveZoneEi"
_SYM_KBD   = "_ZN12LayerShellQt6Window24setKeyboardInteractivityENS0_21KeyboardInteractivityE"

# Geometry. The surface is ALWAYS this tall (= expanded) in morph mode.
HEADER_H   = 80
CONTENT_H  = 300
GAP        = 12
MARGIN     = 10
SURFACE_H  = MARGIN + HEADER_H + GAP + CONTENT_H + MARGIN   # 412

CARD_QSS = (
    "background-color: rgba(15, 17, 25, 215);"
    " border: 1px solid black; border-radius: 12px;"
)


def configure_layer_surface(widget: QWidget) -> bool:
    """Attach LayerShellQt config (header anchor, OVERLAY) to widget's QWindow."""
    try:
        lib = ctypes.CDLL(_LIB)
    except OSError as exc:
        print(f"[spike] cannot load {_LIB}: {exc}")
        return False

    lib._get = getattr(lib, _SYM_GET)
    lib._get.restype = ctypes.c_void_p
    lib._get.argtypes = [ctypes.c_void_p]
    for name, sym in (("_layer", _SYM_LAYER), ("_anch", _SYM_ANCH),
                      ("_excl", _SYM_EXCL), ("_kbd", _SYM_KBD)):
        fn = getattr(lib, sym)
        fn.restype = None
        fn.argtypes = [ctypes.c_void_p, ctypes.c_int]
        setattr(lib, name, fn)

    qwin = widget.windowHandle()
    if qwin is None:
        print("[spike] windowHandle() is None — call winId() first")
        return False

    ls_window = lib._get(sip.unwrapinstance(qwin))
    if not ls_window:
        print("[spike] LayerShellQt::Window::get() returned null")
        return False

    lib._layer(ls_window, LAYER_OVERLAY)
    lib._anch(ls_window, ANCHOR_HEADER)
    lib._excl(ls_window, 0)            # like the hint bar: don't reserve space
    lib._kbd(ls_window, KBD_ON_DEMAND)
    print("[spike] layer surface: OVERLAY anchors=TOP|L|R excl=0 kbd=ON_DEMAND")
    return True


class HomeSurface(QWidget):
    """One persistently-mapped surface: fixed header + morphing content."""

    def __init__(self, resize_mode: bool) -> None:
        super().__init__()
        self._resize_mode = resize_mode
        self._expanded = False

        self.setWindowTitle("KD Home surface spike")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        # Morph mode: surface is ALWAYS the expanded height; only the inner
        # content widget grows/shrinks. Resize mode: surface itself resizes.
        self.setFixedHeight(self._collapsed_h() if resize_mode else SURFACE_H)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, MARGIN, 16, MARGIN)
        outer.setSpacing(GAP)

        outer.addWidget(self._build_header())
        self._content = self._build_content()
        outer.addWidget(self._content)
        outer.addStretch(1)   # absorbs slack in morph mode while content is short

        # Inner morph: animate the content's max-height and opacity together.
        self._opacity = QGraphicsOpacityEffect(self._content)
        self._opacity.setOpacity(0.0)
        self._content.setGraphicsEffect(self._opacity)
        self._content.setMaximumHeight(0)

        self._anim = QParallelAnimationGroup(self)
        a_h = QPropertyAnimation(self._content, b"maximumHeight")
        a_h.setDuration(180)
        a_h.setEasingCurve(QEasingCurve.Type.OutCubic)
        a_o = QPropertyAnimation(self._opacity, b"opacity")
        a_o.setDuration(180)
        self._anim.addAnimation(a_h)
        self._anim.addAnimation(a_o)
        self._a_h, self._a_o = a_h, a_o

    # ── morph ────────────────────────────────────────────────────────────────

    @staticmethod
    def _collapsed_h() -> int:
        return MARGIN + HEADER_H + MARGIN

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        verb = "EXPAND" if expanded else "COLLAPSE"

        if self._resize_mode:
            # Contrast path: resize the actual top-level surface. On Wayland this
            # re-commits the layer surface size (set_size) on every toggle — the
            # thing morph mode avoids. Kept crude on purpose.
            self.setFixedHeight(SURFACE_H if expanded else self._collapsed_h())
            self._content.setMaximumHeight(CONTENT_H if expanded else 0)
            self._opacity.setOpacity(1.0 if expanded else 0.0)
            print(f"[spike] {verb}: RESIZED surface → {self.height()}px (re-commits set_size)")
            return

        print(f"[spike] {verb}: surface stays {self.height()}px, morphing inner content only")

        self._anim.stop()
        self._a_h.setStartValue(self._content.maximumHeight())
        self._a_h.setEndValue(CONTENT_H if expanded else 0)
        self._a_o.setStartValue(self._opacity.opacity())
        self._a_o.setEndValue(1.0 if expanded else 0.0)
        self._anim.start()

    # ── header (top-bar role: clock, date, network, notifications) ────────────

    def _build_header(self) -> QWidget:
        card = QWidget()
        card.setObjectName("header")
        card.setFixedHeight(HEADER_H)
        card.setStyleSheet("#header {" + CARD_QSS + "}")

        row = QHBoxLayout(card)
        row.setContentsMargins(24, 0, 24, 0)

        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet(
            "font-size: 26px; color: white; background: transparent;")
        row.addWidget(self._date_lbl)
        row.addSpacing(24)

        self._clock_lbl = QLabel()
        self._clock_lbl.setStyleSheet(
            "font-size: 26px; color: white; background: transparent;")
        row.addWidget(self._clock_lbl)

        row.addStretch(1)

        net = QLabel()
        net.setPixmap(qta.icon("fa5s.wifi", color="white").pixmap(QSize(24, 24)))
        net.setStyleSheet("background: transparent;")
        row.addWidget(net)
        row.addSpacing(18)

        # Notification glyph + red count badge (top-bar parity).
        bell_wrap = QWidget()
        bell_wrap.setFixedSize(40, 40)
        bell_wrap.setStyleSheet("background: transparent;")
        bell = QLabel(bell_wrap)
        bell.setPixmap(qta.icon("fa5s.bell", color="white").pixmap(QSize(24, 24)))
        bell.move(2, 8)
        badge = QLabel("3", bell_wrap)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            "background-color: #bf616a; color: white; font-size: 10px;"
            " font-weight: bold; border-radius: 9px;")
        badge.setFixedSize(18, 18)
        badge.move(20, 2)
        row.addWidget(bell_wrap)

        self._tick_clock()
        timer = QTimer(self)
        timer.timeout.connect(self._tick_clock)
        timer.start(1000)
        return card

    def _tick_clock(self) -> None:
        now = QDateTime.currentDateTime().toPyDateTime()
        loc = QLocale.system()
        day = loc.dayName(now.weekday() + 1, QLocale.FormatType.LongFormat)
        month = loc.monthName(now.month, QLocale.FormatType.ShortFormat)
        self._date_lbl.setText(f"{day}  {now.day:02d} {month}. {now.year}")
        self._clock_lbl.setText(now.strftime("%H:%M:%S"))

    # ── content (expanded: stand-in for §7.10 Home Overlay sections) ──────────

    def _build_content(self) -> QWidget:
        card = QWidget()
        card.setObjectName("content")
        card.setStyleSheet("#content {" + CARD_QSS + "}")

        col = QVBoxLayout(card)
        col.setContentsMargins(28, 22, 28, 22)
        col.setSpacing(18)

        title = QLabel("Quick adjust")
        title.setStyleSheet(
            "color:#88c0d0; font-size:15px; font-weight:bold; background:transparent;")
        col.addWidget(title)

        slider_row = QHBoxLayout()
        vol = QLabel()
        vol.setPixmap(qta.icon("fa5s.volume-up", color="white").pixmap(QSize(22, 22)))
        vol.setStyleSheet("background: transparent;")
        slider_row.addWidget(vol)
        slider_row.addSpacing(12)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setValue(80)
        slider.setStyleSheet(
            "QSlider::groove:horizontal{height:8px;background:#4c566a;border-radius:4px;}"
            "QSlider::sub-page:horizontal{background:#88c0d0;border-radius:4px;}"
            "QSlider::handle:horizontal{width:22px;height:22px;margin:-7px 0;"
            "background:white;border-radius:11px;}")
        slider_row.addWidget(slider, 1)
        col.addLayout(slider_row)

        actions = QLabel("Actions")
        actions.setStyleSheet(
            "color:#88c0d0; font-size:15px; font-weight:bold; background:transparent;")
        col.addWidget(actions)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        for label, glyph in (("Power", "fa5s.power-off"),
                             ("Network", "fa5s.wifi"),
                             ("Notifications", "fa5s.bell")):
            cards.addWidget(self._action_card(label, glyph))
        col.addLayout(cards)
        col.addStretch(1)
        return card

    @staticmethod
    def _action_card(label: str, glyph: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet(
            "background-color:#2e3440; border:1px solid #3b4252; border-radius:10px;")
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 14, 0, 14)
        v.setSpacing(8)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel()
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setPixmap(qta.icon(glyph, color="white").pixmap(QSize(28, 28)))
        icon.setStyleSheet("background: transparent; border: none;")
        v.addWidget(icon)
        txt = QLabel(label)
        txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        txt.setStyleSheet("color:white; font-size:13px; background:transparent; border:none;")
        v.addWidget(txt)
        return w

    # ── input ─────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            QApplication.instance().quit()
        elif event.key() == Qt.Key.Key_Space:
            self.toggle()
        else:
            super().keyPressEvent(event)


def main() -> int:
    resize_mode = os.environ.get("SPIKE_RESIZE") == "1"
    app = QApplication(sys.argv)
    global qta
    import qtawesome as qta   # now that QApplication exists (see note at import)
    print(f"[spike] Qt platform: {app.platformName()}")
    print(f"[spike] mode: {'RESIZE surface (contrast)' if resize_mode else 'inner morph (target)'}")

    w = HomeSurface(resize_mode)
    w.winId()
    if not configure_layer_surface(w):
        print("[spike] FALLBACK: layer-shell config failed; plain top-level window")
    w.show()
    w.activateWindow()

    # Auto-cycle so the morph can be judged without hand timing.
    cycle = QTimer(w)
    cycle.timeout.connect(w.toggle)
    cycle.start(2500)

    SECONDS = 90
    QTimer.singleShot(SECONDS * 1000, app.quit)
    print(f"[spike] auto-cycling collapse↔expand every 2.5s for {SECONDS}s "
          "(Space = toggle, Esc = quit)")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
