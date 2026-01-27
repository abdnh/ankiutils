from __future__ import annotations

import json
import urllib
import urllib.parse
from typing import Any, Callable

from anki.utils import pointVersion
from aqt.qt import (
    QObject,
    Qt,
    QUrl,
    QVBoxLayout,
    QWebEngineNewWindowRequest,
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineUrlRequestInfo,
    QWebEngineUrlRequestInterceptor,
    QWidget,
    qconnect,
)
from aqt.theme import theme_manager
from aqt.utils import openLink
from aqt.webview import AnkiWebPage, AnkiWebView
from structlog.stdlib import BoundLogger

from ..consts import AddonConsts
from ..sveltekit import _APIKEY, SveltekitServer, get_api_host, is_hmr_enabled
from .dialog import Dialog

profile_with_api_access: QWebEngineProfile | None = None


class AuthInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, consts: AddonConsts, parent: QObject | None = None):
        super().__init__(parent)
        self.consts = consts

    def interceptRequest(self, info: QWebEngineUrlRequestInfo) -> None:
        if info.requestUrl().host() == get_api_host(self.consts):
            info.setHttpHeader(b"Authorization", f"Bearer {_APIKEY}".encode())


class SvelteWebPage(AnkiWebPage):
    def __init__(
        self, on_bridge_cmd: Callable[[str], Any], parent: QObject, consts: AddonConsts
    ):
        self.consts = consts
        global profile_with_api_access
        profile = profile_with_api_access
        if not profile:
            profile = QWebEngineProfile()
            interceptor = AuthInterceptor(self.consts, profile)
            profile.setUrlRequestInterceptor(interceptor)
            profile_with_api_access = profile

        if pointVersion() >= 250204:
            from aqt.webview import AnkiWebViewKind, _bridge_script  # noqa: PLC0415

            self._inject_user_script(profile, _bridge_script)
            self._kind = AnkiWebViewKind.DEFAULT

        self._onBridgeCmd = on_bridge_cmd
        QWebEnginePage.__init__(self, profile, parent)
        self._setupBridge()
        qconnect(self.newWindowRequested, self.on_new_window_requested)

    def createWindow(self, type: QWebEnginePage.WebWindowType) -> None:
        return None

    def on_new_window_requested(self, request: QWebEngineNewWindowRequest) -> None:
        openLink(request.requestedUrl())


class SveltekitWebDialog(Dialog):
    default_size = (800, 800)

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
        self.use_standard_anki_styling = False
        self.server.register_page(path)
        super().__init__(consts=consts, parent=parent, flags=flags, subtitle=subtitle)

    def setup_ui(self) -> None:
        qconnect(self.finished, self._cleanup)
        layout = QVBoxLayout()
        self.setLayout(layout)
        title = self.consts.name
        if self.subtitle:
            title += f" - {self.subtitle}"
        self.web = AnkiWebView(self, title)
        self.web.setPage(SvelteWebPage(self.web._onBridgeCmd, self.web, self.consts))
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
        if self.use_standard_anki_styling:
            funcs = [
                "add_dynamic_styling_and_props_then_show",
                "add_dynamic_css_and_classes_then_show",
                "inject_dynamic_style_and_show",
            ]
            for func in funcs:
                try:
                    getattr(self.web, func)()
                except AttributeError:
                    continue
                else:
                    return
        else:
            body_classes = theme_manager.body_class().split(" ")
            self.web.evalWithCallback(
                f"document.body.classList.add(...{json.dumps(body_classes)})",
                lambda _: self.web.show(),
            )

    def _cleanup(self) -> None:
        self.server.remove_proto_handlers_for_dialog(self)
        self.web.cleanup()
