from __future__ import annotations

from aqt.qt import Qt, QUrl, QVBoxLayout, QWidget
from aqt.webview import AnkiWebView
from structlog.stdlib import BoundLogger

from ..consts import AddonConsts
from ..sveltekit import SveltekitServer
from .dialog import Dialog


class SveltekitWebDialog(Dialog):
    def __init__(
        self,
        consts: AddonConsts,
        logger: BoundLogger,
        server: SveltekitServer,
        path: str,
        parent: QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
        subtitle: str = "",
    ):
        self.web: AnkiWebView
        self.consts = consts
        self.logger = logger
        self.server = server
        self.path = path
        super().__init__(
            consts=consts, parent=parent, flags=Qt.WindowType.Window, subtitle=subtitle
        )

    def setup_ui(self) -> None:
        layout = QVBoxLayout()
        self.setLayout(layout)
        title = f"{self.consts.name} - {self.subtitle}"
        self.web = AnkiWebView(self, title)
        self.web.set_title(title)
        layout.addWidget(self.web)
        self.web.set_bridge_command(self.on_bridge_command, self)
        super().setup_ui()
        self._load_page()

    def on_bridge_command(self, message: str) -> None:
        self.logger.warning("Unhandled bridge command", message=message)

    def _load_page(self) -> None:
        self.web.set_open_links_externally(False)
        self.web.load_url(QUrl(f"{self.server.get_url()}/{self.path}"))
        self.web.add_dynamic_styling_and_props_then_show()
