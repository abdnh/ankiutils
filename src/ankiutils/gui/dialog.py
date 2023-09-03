from typing import Optional

from aqt import mw
from aqt.qt import *
from aqt.utils import restoreGeom, saveGeom


class Dialog(QDialog):
    key: str = ""

    def __init__(
        self,
        module: str,
        parent: Optional[QWidget] = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        self._addon = mw.addonManager.addonFromModule(module)
        self.setup_ui()

    def setup_ui(self) -> None:
        restoreGeom(self, f"{self._addon}_{self.key}")

    def closeEvent(self, event: QCloseEvent) -> None:
        saveGeom(self, f"{self._addon}_{self.key}")
        return super().closeEvent(event)
