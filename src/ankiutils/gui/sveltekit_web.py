from __future__ import annotations

import urllib
import urllib.parse
from typing import Any

from aqt.qt import Qt, QUrl, QVBoxLayout, QWidget, qconnect
from aqt.theme import theme_manager
from aqt.webview import AnkiWebView
from structlog.stdlib import BoundLogger

from ..consts import AddonConsts
from ..sveltekit import SveltekitServer, is_hmr_enabled
from .dialog import Dialog


class SveltekitWebDialog(Dialog):
    def __init__(
        self,
        consts: AddonConsts,
        logger: BoundLogger,
        server: SveltekitServer,
        path: str,
        parent: QWidget | None = None,
        flags: Qt.WindowType = Qt.WindowType.Window,
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
        qconnect(self.finished, self._cleanup)
        layout = QVBoxLayout()
        self.setLayout(layout)
        title = self.consts.name
        if self.subtitle:
            title += f" - {self.subtitle}"
        self.web = AnkiWebView(self, title)
        self.web.set_title(title)
        layout.addWidget(self.web)
        self.web.set_bridge_command(self.on_bridge_command, self)
        super().setup_ui()
        self._load_page()

    def on_bridge_command(self, message: str) -> Any:
        self.logger.warning("Unhandled bridge command", message=message)

    def get_query_params(self) -> dict[str, Any]:
        return {"id": id(self)}

    def _load_page(self) -> None:
        self.web.set_open_links_externally(False)
        if theme_manager.night_mode:
            extra = "#night"
        else:
            extra = ""

        if is_hmr_enabled(self.consts):
            server = "http://127.0.0.1:5174"
        else:
            server = self.server.get_url()
        query_string = urllib.parse.urlencode(self.get_query_params())
        self.web.load_url(QUrl(f"{server}/{self.path}?{query_string}{extra}"))
        self.web.add_dynamic_styling_and_props_then_show()

    def _cleanup(self) -> None:
        self.server.remove_proto_handlers_for_dialog(self)
        self.web.cleanup()
