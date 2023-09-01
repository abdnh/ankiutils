import typing

from aqt.qt import *
from aqt.utils import restoreGeom, saveGeom

from ..config import ADDON_MODULE


class Dialog(QDialog):
    key: str = ""

    def __init__(
        self,
        parent: typing.Optional[QWidget],
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self.setup_ui()

    def setup_ui(self) -> None:
        restoreGeom(self, f"{ADDON_MODULE}_{self.key}")

    def closeEvent(self, event: QCloseEvent) -> None:
        saveGeom(self, f"{ADDON_MODULE}_{self.key}")
        return super().closeEvent(event)
