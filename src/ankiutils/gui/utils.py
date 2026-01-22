from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Callable

import aqt
from aqt.qt import QMessageBox, QPixmap, Qt, QWidget, qconnect
from aqt.theme import theme_manager
from aqt.utils import tr


# Credit: Adapted from aqt.utils
class MessageBox(QMessageBox):
    def __init__(
        self,
        text: str,
        callback: Callable[[int], None] | None = None,
        parent: QWidget | None = None,
        icon: QMessageBox.Icon = QMessageBox.Icon.NoIcon,
        title: str = "Anki",
        buttons: (
            Sequence[
                str | QMessageBox.StandardButton | tuple[str, QMessageBox.ButtonRole]
            ]
            | None
        ) = None,
        default_button: int = 0,
        textFormat: Qt.TextFormat = Qt.TextFormat.PlainText,
        modality: Qt.WindowModality = Qt.WindowModality.WindowModal,
    ) -> None:
        parent = parent or aqt.mw.app.activeWindow() or aqt.mw
        super().__init__(parent)
        self.setText(text)
        self.setWindowTitle(title)
        self.setWindowModality(modality)
        self.setIcon(icon)
        if icon == QMessageBox.Icon.Question and theme_manager.night_mode:
            img = self.iconPixmap().toImage()
            img.invertPixels()
            self.setIconPixmap(QPixmap(img))
        self.setTextFormat(textFormat)
        if buttons is None:
            buttons = [QMessageBox.StandardButton.Ok]
        for i, button in enumerate(buttons):
            if isinstance(button, str):
                b = self.addButton(button, QMessageBox.ButtonRole.ActionRole)
            elif isinstance(button, QMessageBox.StandardButton):
                b = self.addButton(button)
                if button == QMessageBox.StandardButton.Discard:
                    assert b is not None
                    b.setText(tr.actions_discard())
            elif isinstance(button, tuple):
                b = self.addButton(button[0], button[1])
            else:
                continue
            if callback is not None:
                assert b is not None
                qconnect(b.clicked, partial(callback, i))
            if i == default_button:
                self.setDefaultButton(b)

        self.open()
