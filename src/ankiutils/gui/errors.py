from __future__ import annotations

from aqt import mw
from aqt.qt import QMessageBox, Qt, QWidget
from aqt.utils import tooltip

from ..errors import ErrorReportingArgs, LogsUpload, upload_logs_op
from .utils import MessageBox


def upload_logs_and_notify_user(parent: QWidget, args: ErrorReportingArgs) -> None:
    def on_success(upload: LogsUpload | None) -> None:
        if not upload:
            tooltip("Failed to upload logs. Issue has been reported.", parent=parent)
            return

        def callback(_: int) -> None:
            mw.app.clipboard().setText(upload.filename)

        MessageBox(
            text=f"Logs uploaded to file {upload.filename}.<br>"
            "Please share it using one of the following support channels:<br><br>"
            + "<br>".join(
                f"<a href='{url}'>{url}</a>"
                for url in args.consts.support_channels.values()
            ),
            title=args.consts.name,
            parent=parent,
            textFormat=Qt.TextFormat.RichText,
            buttons=["Copy filename"],
            icon=QMessageBox.Icon.Information,
            callback=callback,
        )

    upload_logs_op(parent=parent, args=args, on_success=on_success).run_in_background()
