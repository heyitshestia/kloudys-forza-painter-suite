from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


class CommunityApiError(RuntimeError):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = int(status)
        self.code = str(code or "request_failed")
        self.message = str(message or "The community request failed.")


class CommunityApiClient:
    def __init__(self, base_url: str, token: str = "", test_auth_token: str = ""):
        self.base_url = str(base_url or "").rstrip("/")
        self.token = str(token or "")
        self.test_auth_token = str(test_auth_token or "")
        parsed = urllib.parse.urlsplit(self.base_url)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment
        ):
            raise CommunityApiError(0, "invalid_service_url", "The community service URL is invalid.")
        if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise CommunityApiError(0, "insecure_service_url", "The community service must use HTTPS outside local testing.")
        self._origin = (parsed.scheme.lower(), parsed.hostname.lower(), parsed.port)
        self._base_path = parsed.path.rstrip("/") + "/"
        self._root_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))

    def url(self, path: str) -> str:
        value = str(path or "")
        if value.startswith(("http://", "https://")):
            candidate = value
        elif value.startswith("/"):
            candidate = self._root_url + value
        else:
            candidate = self.base_url + "/" + value.lstrip("/")
        parsed = urllib.parse.urlsplit(candidate)
        origin = (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port)
        if (
            origin != self._origin
            or parsed.username
            or parsed.password
            or parsed.fragment
            or not parsed.path.startswith(self._base_path)
        ):
            raise CommunityApiError(502, "untrusted_asset_url", "The community service returned an untrusted asset URL.")
        return candidate

    def json(self, path: str, method: str = "GET", payload=None, authenticated: bool = False, maximum: int = 36 * 1024 * 1024):
        data = None if payload is None else json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        target_url = self.url(path)
        headers = {
            "Accept": "application/json",
            "User-Agent": "KFPS-Community-Client/1",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.test_auth_token and target_url == self.url("auth/test"):
            headers["X-Community-Test-Token"] = self.test_auth_token
        if authenticated:
            if not self.token:
                raise CommunityApiError(401, "authentication_required", "Sign in to use this community feature.")
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(target_url, data=data, method=method, headers=headers)
        raw, _headers = self._open(request, maximum)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise CommunityApiError(502, "invalid_service_response", "The community service returned invalid JSON.") from exc

    def binary(self, path: str, authenticated: bool = False, maximum: int = 26 * 1024 * 1024):
        headers = {"Accept": "*/*", "User-Agent": "KFPS-Community-Client/1"}
        if authenticated:
            if not self.token:
                raise CommunityApiError(401, "authentication_required", "Sign in to use this community feature.")
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(self.url(path), method="GET", headers=headers)
        return self._open(request, maximum)

    @staticmethod
    def _open(request: urllib.request.Request, maximum: int):
        try:
            with _OPENER.open(request, timeout=30) as response:
                declared = int(response.headers.get("Content-Length") or 0)
                if declared > maximum:
                    raise CommunityApiError(413, "response_too_large", "The community response is too large.")
                raw = response.read(maximum + 1)
                if len(raw) > maximum:
                    raise CommunityApiError(413, "response_too_large", "The community response is too large.")
                return raw, dict(response.headers.items())
        except urllib.error.HTTPError as error:
            raw = error.read(256 * 1024)
            try:
                payload = json.loads(raw.decode("utf-8"))
                code = str(payload.get("error") or "request_failed")
                message = str(payload.get("message") or code.replace("_", " ").capitalize())
            except Exception:
                code = "request_failed"
                message = f"Community request failed with HTTP {error.code}."
            raise CommunityApiError(error.code, code, message) from error
        except CommunityApiError:
            raise
        except Exception as exc:
            raise CommunityApiError(0, "service_unavailable", "The community service is unavailable.") from exc


def build_query(path: str, values: dict) -> str:
    filtered = {key: value for key, value in values.items() if value not in (None, "")}
    return path + ("?" + urllib.parse.urlencode(filtered) if filtered else "")
