from __future__ import annotations

from anki.utils import pointVersion
from aqt import mw
from aqt.qt import QDialog, Qt, QWidget, qconnect
from aqt.utils import restoreGeom, saveGeom

from ..consts import AddonConsts


class Dialog(QDialog):
    key: str = ""
    default_size: tuple[int, int] | None = None

    def __init__(
        self,
        consts: AddonConsts,
        parent: QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
        subtitle: str = "",
    ) -> None:
        self.consts = consts
        self.subtitle = ""
        super().__init__(parent, flags)
        qconnect(self.finished, self._on_finished)
        if hasattr(mw, "garbage_collect_on_dialog_finish"):
            mw.garbage_collect_on_dialog_finish(self)
        self.setup_ui()

    def setup_ui(self) -> None:
        if pointVersion() >= 55:
            restoreGeom(
                self, f"{self.consts.module}_{self.key}", default_size=self.default_size
            )
        else:
            restoreGeom(self, f"{self.consts.module}_{self.key}")
        title = self.consts.name
        if self.subtitle:
            title += f" - {self.subtitle}"
        self.setWindowTitle(title)

    def _on_finished(self) -> None:
        saveGeom(self, f"{self.consts.module}_{self.key}")
