from __future__ import annotations

import json
from urllib.parse import urlparse

from PySide6.QtCore import QByteArray, QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .activation_config import NETWORK_TIMEOUT_MS, PROTOCOL_VERSION


class ActivationClient(QObject):
    completed = Signal(object)

    def __init__(self, endpoint: str, parent=None):
        super().__init__(parent)
        self._endpoint = endpoint.rstrip("/")
        self._manager = QNetworkAccessManager(self)
        self._manager.setTransferTimeout(NETWORK_TIMEOUT_MS)
        self._contexts: dict[QNetworkReply, dict] = {}

    @property
    def configured(self) -> bool:
        if not self._endpoint:
            return False
        parsed = urlparse(self._endpoint)
        secure = parsed.scheme == "https"
        local_test = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        return bool(
            (secure or local_test)
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and parsed.path in {"", "/"}
            and not parsed.params
            and not parsed.query
            and not parsed.fragment
        )

    def activate(self, *, key_id: str, key_proof: str, device_id: str, nonce: str):
        self._send("activate", key_id=key_id, key_proof=key_proof, device_id=device_id, nonce=nonce)

    def deactivate(self, *, key_id: str, key_proof: str, device_id: str, nonce: str):
        self._send("deactivate", key_id=key_id, key_proof=key_proof, device_id=device_id, nonce=nonce)

    def _send(self, operation: str, *, key_id: str, key_proof: str, device_id: str, nonce: str):
        if not self.configured:
            self.completed.emit({
                "operation": operation,
                "nonce": nonce,
                "http_status": 0,
                "network_error": "activation service is not configured",
                "body": None,
            })
            return
        request = QNetworkRequest(QUrl(f"{self._endpoint}/v1/{operation}"))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setRawHeader(b"Accept", b"application/json")
        request.setRawHeader(b"Cache-Control", b"no-store")
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        request.setTransferTimeout(NETWORK_TIMEOUT_MS)
        payload = json.dumps({
            "protocol": PROTOCOL_VERSION,
            "key_id": key_id,
            "key_proof": key_proof,
            "device_id": device_id,
            "nonce": nonce,
        }, separators=(",", ":")).encode("utf-8")
        reply = self._manager.post(request, QByteArray(payload))
        self._contexts[reply] = {"operation": operation, "nonce": nonce}
        reply.finished.connect(lambda current=reply: self._finished(current))

    def _finished(self, reply: QNetworkReply):
        context = self._contexts.pop(reply, {"operation": "", "nonce": ""})
        status_value = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        try:
            status = int(status_value or 0)
        except (TypeError, ValueError):
            status = 0
        raw = bytes(reply.readAll())
        body = None
        parse_error = ""
        if len(raw) > 64 * 1024:
            parse_error = "activation response was too large"
        elif raw:
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                parse_error = "activation response was not valid JSON"
        network_error = ""
        if status == 0 and reply.error() != QNetworkReply.NoError:
            network_error = reply.errorString() or "activation request failed"
        self.completed.emit({
            **context,
            "http_status": status,
            "network_error": network_error,
            "parse_error": parse_error,
            "body": body,
        })
        reply.deleteLater()
