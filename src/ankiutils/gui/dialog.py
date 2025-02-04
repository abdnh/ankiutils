from typing import Optional

from anki.utils import pointVersion
from aqt import mw
from aqt.qt import *
from aqt.utils import restoreGeom, saveGeom


class Dialog(QDialog):
    key: str = ""
    default_size: Optional[tuple[int, int]] = None

    def __init__(
        self,
        module: str,
        parent: Optional[QWidget] = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
    ) -> None:
        super().__init__(parent, flags)
        qconnect(self.finished, self._on_finished)
        if hasattr(mw, "garbage_collect_on_dialog_finish"):
            mw.garbage_collect_on_dialog_finish(self)
        self._addon = mw.addonManager.addonFromModule(module)
        self.setup_ui()

    def setup_ui(self) -> None:
        if pointVersion() >= 55:
            restoreGeom(
                self, f"{self._addon}_{self.key}", default_size=self.default_size
            )
        else:
            restoreGeom(self, f"{self._addon}_{self.key}")

    def _on_finished(self) -> None:
        saveGeom(self, f"{self._addon}_{self.key}")
