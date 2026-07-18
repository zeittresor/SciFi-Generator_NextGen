from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

REQUIRED_KEYS = {
    "window_bg", "window_text", "panel_bg", "input_bg", "input_text",
    "button_bg", "button_text", "button_hover", "button_pressed",
    "border", "disabled_bg", "disabled_text", "selection_bg",
    "selection_text", "accent", "progress_bg", "progress_text",
    "tooltip_bg", "tooltip_text",
}


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    source: Path
    palette: dict[str, str]

    def stylesheet(self, scale: float = 1.0) -> str:
        p = self.palette
        px = lambda value: max(1, round(value * scale))
        return f"""
QMainWindow, QWidget {{
    background-color: {p['window_bg']};
    color: {p['window_text']};
}}
QMenuBar, QMenu {{
    background-color: {p['panel_bg']};
    color: {p['window_text']};
}}
QMenuBar::item {{
    padding: {px(4)}px {px(7)}px;
}}
QMenuBar::item:selected, QMenu::item:selected {{
    background-color: {p['selection_bg']};
    color: {p['selection_text']};
}}
QTabWidget::pane {{
    border: 1px solid {p['border']};
    background-color: {p['panel_bg']};
}}
QTabBar::tab {{
    background-color: {p['button_bg']};
    color: {p['button_text']};
    border: 1px solid {p['border']};
    padding: {px(7)}px {px(12)}px;
}}
QTabBar::tab:selected, QTabBar::tab:hover {{
    background-color: {p['button_hover']};
    color: {p['button_text']};
}}
QTextEdit, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListView, QAbstractItemView {{
    background-color: {p['input_bg']};
    color: {p['input_text']};
    border: 1px solid {p['border']};
    selection-background-color: {p['selection_bg']};
    selection-color: {p['selection_text']};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    min-height: {px(26)}px;
    padding: {px(2)}px {px(5)}px;
}}
QComboBox QAbstractItemView {{
    background-color: {p['input_bg']};
    color: {p['input_text']};
    selection-background-color: {p['selection_bg']};
    selection-color: {p['selection_text']};
}}
QPushButton {{
    min-height: {px(28)}px;
    background-color: {p['button_bg']};
    color: {p['button_text']};
    border: 1px solid {p['border']};
    padding: {px(4)}px {px(9)}px;
}}
QPushButton:hover {{
    background-color: {p['button_hover']};
    color: {p['button_text']};
}}
QPushButton:pressed {{
    background-color: {p['button_pressed']};
    color: {p['button_text']};
}}
QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled {{
    background-color: {p['disabled_bg']};
    color: {p['disabled_text']};
    border-color: {p['border']};
}}
QGroupBox {{
    font-weight: 600;
    border: 1px solid {p['border']};
    margin-top: {px(9)}px;
    padding-top: {px(9)}px;
    background-color: {p['panel_bg']};
    color: {p['window_text']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {px(8)}px;
    padding: 0 {px(4)}px;
    color: {p['window_text']};
}}
QLabel, QCheckBox, QRadioButton {{
    color: {p['window_text']};
}}
QCheckBox {{
    spacing: {px(6)}px;
}}
QCheckBox::indicator {{
    width: {px(15)}px;
    height: {px(15)}px;
}}
QProgressBar {{
    background-color: {p['progress_bg']};
    color: {p['progress_text']};
    border: 1px solid {p['border']};
    text-align: center;
    min-height: {px(18)}px;
}}
QProgressBar::chunk {{
    background-color: {p['accent']};
}}
QSlider {{
    min-height: {px(24)}px;
}}
QSlider::groove:horizontal {{
    height: {px(6)}px;
    background-color: {p['progress_bg']};
    border: 1px solid {p['border']};
}}
QSlider::handle:horizontal {{
    width: {px(16)}px;
    margin: -{px(6)}px 0;
    border: 1px solid {p['border']};
    background-color: {p['accent']};
}}
QToolTip {{
    background-color: {p['tooltip_bg']};
    color: {p['tooltip_text']};
    border: 1px solid {p['border']};
    padding: {px(4)}px;
}}
QScrollBar:vertical {{
    width: {px(14)}px;
    background-color: {p['panel_bg']};
    border: 1px solid {p['border']};
}}
QScrollBar:horizontal {{
    height: {px(14)}px;
    background-color: {p['panel_bg']};
    border: 1px solid {p['border']};
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background-color: {p['button_bg']};
    min-height: {px(22)}px;
    min-width: {px(22)}px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background-color: {p['button_hover']};
}}
"""



def _rgb(color: str) -> tuple[float, float, float]:
    return tuple(int(color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def contrast_ratio(first: str, second: str) -> float:
    lum = []
    for color in (first, second):
        r, g, b = _rgb(color)
        lum.append(0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b))
    lighter, darker = max(lum), min(lum)
    return (lighter + 0.05) / (darker + 0.05)


class ThemeManager:
    def __init__(self, theme_dir: Path):
        self.theme_dir = Path(theme_dir)
        self.themes: dict[str, Theme] = {}
        self.errors: list[str] = []

    def load(self) -> None:
        self.themes.clear()
        self.errors.clear()
        self.theme_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.theme_dir.glob("*.json"), key=lambda p: p.name.lower()):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                name = str(payload["name"]).strip()
                palette = dict(payload["palette"])
                description = str(payload.get("description", "")).strip()
                self._validate(name, palette)
                if name in self.themes:
                    raise ValueError(f"Theme-Name ist doppelt: {name}")
                self.themes[name] = Theme(name, description, path, palette)
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                self.errors.append(f"{path.name}: {exc}")

    @staticmethod
    def _validate(name: str, palette: dict[str, str]) -> None:
        if not name:
            raise ValueError("Theme-Name fehlt")
        missing = sorted(REQUIRED_KEYS - set(palette))
        if missing:
            raise ValueError("fehlende Farben: " + ", ".join(missing))
        invalid = [key for key in REQUIRED_KEYS if not _HEX.match(str(palette[key]))]
        if invalid:
            raise ValueError("ungültige #RRGGBB-Werte: " + ", ".join(sorted(invalid)))

        checks = (
            ("Fenstertext", palette["window_text"], palette["window_bg"], 4.5),
            ("Paneltext", palette["window_text"], palette["panel_bg"], 4.5),
            ("Eingabetext", palette["input_text"], palette["input_bg"], 4.5),
            ("Schaltflächentext", palette["button_text"], palette["button_bg"], 4.5),
            ("Schaltflächentext/Hover", palette["button_text"], palette["button_hover"], 4.5),
            ("Schaltflächentext/Gedrückt", palette["button_text"], palette["button_pressed"], 4.5),
            ("Auswahltext", palette["selection_text"], palette["selection_bg"], 4.5),
            ("Fortschrittstext/Hintergrund", palette["progress_text"], palette["progress_bg"], 4.5),
            ("Fortschrittstext/Balken", palette["progress_text"], palette["accent"], 4.5),
            ("Tooltiptext", palette["tooltip_text"], palette["tooltip_bg"], 4.5),
            ("Deaktivierter Text", palette["disabled_text"], palette["disabled_bg"], 3.0),
        )
        failures = []
        for label, fg, bg, minimum in checks:
            ratio = contrast_ratio(fg, bg)
            if ratio < minimum:
                failures.append(f"{label} {ratio:.2f}:1 (mindestens {minimum:.1f}:1)")
        if failures:
            raise ValueError("Kontrastprüfung fehlgeschlagen: " + "; ".join(failures))

    def names(self) -> list[str]:
        return list(self.themes)

    def get(self, name: str) -> Theme | None:
        return self.themes.get(name)
