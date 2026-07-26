from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .app_paths import AppPaths
from .community_client import CommunityApiClient, CommunityApiError, build_query
from .community_credentials import CommunityCredentialStore
from .community_validation import CommunityUploadInspection, inspect_upload, validate_download
from .desktop_service import DesktopService
from .log_service import LogService
from .models import DictListModel
from .qt_utils import file_url, safe_file_part


ARTWORK_ROLES = [
    "id", "title", "description", "category", "classification", "classificationLabel", "tagsText", "gamesText", "license",
    "schemaId", "schemaLabel", "schemaKnown", "schemaWarning",
    "shapeCount", "groupCount", "usesMasks", "status", "statusLabel", "rejectionReason", "featured", "supporterOnly", "supporterLabel",
    "revision", "downloads", "favorites", "favorited", "createdAt", "updatedAt", "publishedAt",
    "previewUrl", "thumbnailUrl", "downloadUrl", "contentSha256", "previewSha256", "thumbnailSha256", "creatorName", "creatorAvatar",
    "creatorBio", "creatorFollowers", "creatorFollowed",
]

FEATURED_ARTWORK_LIMIT = 8
SORT_VALUES = ["trending", "new", "downloads", "favorites", "name"]
SORT_LABELS = ["Trending", "Newest", "Most downloaded", "Most favorited", "Name"]
SCOPE_VALUES = ["featured", "browse", "handmade", "toolmade", "supporters", "favorites", "following", "mine"]
SCOPE_LABELS = ["Featured", "Browse", "Handmade", "Toolmade", "Supporters", "Favorites", "Following", "My uploads"]
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_VERIFICATION_URL = "https://github.com/login/device"
LOCAL_COMMUNITY_API_URL = "http://127.0.0.1:8790/v1"


class _GithubNoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


_GITHUB_OPENER = urllib.request.build_opener(_GithubNoRedirect)


def _github_post_json(url, values, maximum=64 * 1024):
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(values).encode("ascii"),
        method="POST",
        headers={"Accept": "application/json", "User-Agent": "KFPS-Community-Client/1"},
    )
    try:
        with _GITHUB_OPENER.open(request, timeout=20) as response:
            declared = int(response.headers.get("Content-Length") or 0)
            if declared > maximum:
                raise CommunityApiError(502, "github_response_too_large", "GitHub returned an unexpected sign-in response.")
            raw = response.read(maximum + 1)
            if len(raw) > maximum:
                raise CommunityApiError(502, "github_response_too_large", "GitHub returned an unexpected sign-in response.")
    except urllib.error.HTTPError as exc:
        raw = exc.read(maximum)
        try:
            payload = json.loads(raw.decode("utf-8"))
            message = str(payload.get("error_description") or payload.get("error") or "GitHub sign-in failed.")
        except Exception:
            message = f"GitHub sign-in failed with HTTP {exc.code}."
        raise CommunityApiError(exc.code, "github_request_failed", message) from exc
    except CommunityApiError:
        raise
    except Exception as exc:
        raise CommunityApiError(0, "github_unavailable", "GitHub sign-in is currently unavailable.") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CommunityApiError(502, "invalid_github_response", "GitHub returned an invalid sign-in response.") from exc
    if not isinstance(payload, dict):
        raise CommunityApiError(502, "invalid_github_response", "GitHub returned an invalid sign-in response.")
    return payload


def community_file_part(value, fallback):
    result = safe_file_part(str(value or ""), fallback)[:64].rstrip(" .") or fallback
    if result.upper() in WINDOWS_RESERVED_NAMES:
        result += "_"
    return result


def _versioned_asset_url(url, digest):
    value = str(url or "")
    checksum = str(digest or "").strip().lower()
    if not value or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        return value
    separator = "&" if "?" in value else "?"
    return f"{value}{separator}v={checksum[:16]}"


def configured_community_api_url(app_root):
    override = os.environ.get("KFPS_COMMUNITY_API_URL", "").strip()
    if override:
        return override.rstrip("/")
    endpoint_file = Path(app_root) / "data" / "community_api_url.txt"
    try:
        configured = endpoint_file.read_text(encoding="utf-8").strip()
    except OSError:
        configured = ""
    return (configured or LOCAL_COMMUNITY_API_URL).rstrip("/")


class CommunityService(QObject):
    changed = Signal()
    supporterEntitlementRequested = Signal(str)
    supporterRepairRequested = Signal()
    _resultReady = Signal(str, object)
    _githubDeviceReady = Signal(object)

    def __init__(
        self, paths: AppPaths, desktop: DesktopService, log: LogService,
        jsons=None, app_version="unknown", demo=False, parent=None,
    ):
        super().__init__(parent)
        self.paths = paths
        self.desktop = desktop
        self.log = log
        self.jsons = jsons
        self.demo = bool(demo)
        self._closed = False
        self._app_version = str(app_version or "unknown").strip()
        self._root = paths.runtime_root / "community"
        self._base_url = configured_community_api_url(paths.app_root)
        self._endpoint_key = hashlib.sha256(self._base_url.encode("utf-8")).hexdigest()[:20]
        self._cache_file = self._catalog_cache_file("featured")
        self._credentials = CommunityCredentialStore(paths.runtime_root, self._base_url)
        self._token = self._credentials.load_token()
        self._github_client_id_override = os.environ.get("KFPS_COMMUNITY_GITHUB_CLIENT_ID", "").strip()[:128]
        self._client = CommunityApiClient(self._base_url, self._token)
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="community")
        self._resultReady.connect(self._apply_result)
        self._githubDeviceReady.connect(self._apply_github_device)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(260)
        self._filter_timer.timeout.connect(self.refresh)
        self._artwork_model = DictListModel(ARTWORK_ROLES)
        self._rows: list[dict] = []
        self._demo_all_rows: list[dict] = []
        self._selected_index = -1
        self._selection_touched = False
        self._selected: dict = {}
        self._profile: dict = {}
        self._config = {
            "categories": ["Characters", "Motorsport", "Logos", "Gaming", "Abstract", "Patterns", "Humor", "Original Artwork", "Other"],
            "games": ["FH5", "FH6", "FM8"],
            "licenses": ["kfps-community-share-v1", "cc-by-4.0", "cc-by-nc-4.0", "cc0-1.0"],
            "classifications": ["handmade", "toolmade"],
            "minimum_upload_version": "3.0.81",
            "test_auth": True,
            "github_client_id": "",
        }
        self._connected = False
        self._busy_count = 0
        self._status = "Community service has not connected yet."
        self._error = ""
        self._search = ""
        self._category = "All"
        self._game = "All"
        self._sort = "trending"
        self._scope = "featured"
        self._creator_filter = ""
        self._page = 1
        self._page_count = 1
        self._total = 0
        self._session_user: dict = {}
        self._session_stats: dict = {}
        self._supporter: dict = {}
        self._supporter_status = "Connect a supporter registration to unlock this catalog."
        self._supporter_entitlement_pending = False
        self._supporter_request_after = 0.0
        self._supporter_request_subject = ""
        self._local_supporter_state = ""
        self._local_supporter_key_available = False
        self._supporter_clear_inflight = False
        self._supporter_clear_after = 0.0
        self._supporter_clear_required = False
        self._upload_inspection: CommunityUploadInspection | None = None
        self._upload_request_generation = 0
        self._upload_status = "Choose an import-ready JSON to prepare an upload."
        self._downloaded_path = ""
        self._github_user_code = ""
        self._github_verification_url = ""
        self._github_code_expires_at = 0.0
        self._authentication_in_progress = False
        self._authentication_provider = ""
        self._github_cancel = threading.Event()
        self._private_preview_inflight: set[str] = set()
        self._supporter_asset_memory: dict[str, str] = {}
        self._supporter_timer = QTimer(self)
        self._supporter_timer.setInterval(5 * 60 * 1000)
        self._supporter_timer.timeout.connect(self._supporter_tick)
        self._supporter_timer.start()
        self._authentication_timer = QTimer(self)
        self._authentication_timer.setInterval(1000)
        self._authentication_timer.timeout.connect(self.changed.emit)
        self._request_generation = 0
        self._load_cache()
        if self.demo:
            self._load_demo_rows()
        QTimer.singleShot(300, self.activate)

    @Property(QObject, constant=True)
    def artworkModel(self):
        return self._artwork_model

    @Property(str, notify=changed)
    def serviceUrl(self):
        return self._base_url

    @Property(bool, notify=changed)
    def connected(self):
        return self._connected

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy_count > 0

    @Property(str, notify=changed)
    def statusMessage(self):
        return self._status

    @Property(str, notify=changed)
    def errorMessage(self):
        return self._error

    @Property("QStringList", notify=changed)
    def categories(self):
        return ["All", *[str(value) for value in self._config.get("categories", [])]]

    @Property("QStringList", notify=changed)
    def games(self):
        return ["All", *[str(value) for value in self._config.get("games", [])]]

    @Property("QStringList", notify=changed)
    def licenses(self):
        return [str(value) for value in self._config.get("licenses", [])]

    @Property("QStringList", constant=True)
    def sortOptions(self):
        return SORT_LABELS

    @Property("QStringList", constant=True)
    def scopeOptions(self):
        return SCOPE_LABELS

    @Property(str, notify=changed)
    def searchQuery(self):
        return self._search

    @Property(str, notify=changed)
    def selectedCategory(self):
        return self._category

    @Property(str, notify=changed)
    def selectedGame(self):
        return self._game

    @Property(int, notify=changed)
    def selectedSortIndex(self):
        return SORT_VALUES.index(self._sort) if self._sort in SORT_VALUES else 0

    @Property(int, notify=changed)
    def selectedScopeIndex(self):
        return SCOPE_VALUES.index(self._scope) if self._scope in SCOPE_VALUES else 0

    @Property(str, notify=changed)
    def creatorFilter(self):
        return self._creator_filter

    @Property(int, notify=changed)
    def page(self):
        return self._page

    @Property(int, notify=changed)
    def pageCount(self):
        return self._page_count

    @Property(int, notify=changed)
    def totalCount(self):
        return self._total

    @Property(int, notify=changed)
    def pageItemCount(self):
        return len(self._rows)

    @Property(str, notify=changed)
    def resultSummary(self):
        if self.busy and not self._rows:
            return "Loading community artwork..."
        if self._scope == "featured":
            noun = "artwork" if len(self._rows) == 1 else "artworks"
            return f"{len(self._rows)} featured {noun}"
        noun = "artwork" if self._total == 1 else "artworks"
        return f"{self._total} {noun}  •  page {self._page} of {self._page_count}"

    @Property(int, notify=changed)
    def selectedIndex(self):
        return self._selected_index

    @Property("QVariantMap", notify=changed)
    def selectedArtwork(self):
        return dict(self._selected)

    @Property(bool, notify=changed)
    def hasSelection(self):
        return bool(self._selected.get("id"))

    @Property(bool, notify=changed)
    def selectedSupporterLocked(self):
        return bool(self._selected.get("supporterOnly")) and not self.supporterAccess

    @Property(bool, notify=changed)
    def canSelectPrevious(self):
        return self._selected_index > 0

    @Property(bool, notify=changed)
    def canSelectNext(self):
        return 0 <= self._selected_index < len(self._rows) - 1

    @Property(bool, notify=changed)
    def selectedOwned(self):
        return bool(self.username and self._selected.get("creatorName") == self.username)

    @Property(bool, notify=changed)
    def selectedMetadataEditable(self):
        return self.authenticated and self.selectedOwned and self._scope == "mine"

    @Property(bool, notify=changed)
    def authenticated(self):
        return bool(self._token and self._session_user)

    @Property(bool, notify=changed)
    def usernameRequired(self):
        return self.authenticated and not bool(self._session_user.get("username"))

    @Property(str, notify=changed)
    def username(self):
        return str(self._session_user.get("username") or "")

    @Property(str, notify=changed)
    def accountLabel(self):
        if self.username:
            return "@" + self.username
        if self.authenticated:
            return "Choose your community username"
        return "Browsing anonymously"

    @Property("QVariantMap", notify=changed)
    def sessionUser(self):
        return dict(self._session_user)

    @Property("QVariantMap", notify=changed)
    def sessionStats(self):
        return dict(self._session_stats)

    @Property(bool, notify=changed)
    def supporterAccess(self):
        if not self.authenticated or not bool(self._supporter.get("active")):
            return False
        expires = self._iso_timestamp(self._supporter.get("verified_until"))
        return expires > time.time()

    @Property(str, notify=changed)
    def supporterStatus(self):
        if self.supporterAccess:
            return "Supporter Community access is verified."
        if self._supporter_entitlement_pending:
            return "Verifying supporter Community access..."
        return self._supporter_status

    @Property(bool, notify=changed)
    def supporterKeyAvailable(self):
        return self._local_supporter_key_available

    @Property(bool, notify=changed)
    def supporterKeyConnected(self):
        return self._local_supporter_state == "active"

    @Property("QVariantMap", notify=changed)
    def creatorProfile(self):
        return dict(self._profile)

    @Property(bool, notify=changed)
    def testAuthenticationAvailable(self):
        return bool(self._config.get("test_auth"))

    @Property(bool, notify=changed)
    def githubAuthenticationAvailable(self):
        return bool(self._github_client_id())

    @Property(bool, notify=changed)
    def authenticationInProgress(self):
        return self._authentication_in_progress

    @Property(str, notify=changed)
    def authenticationProvider(self):
        return self._authentication_provider

    @Property(str, notify=changed)
    def githubUserCode(self):
        return self._github_user_code

    @Property(str, notify=changed)
    def githubVerificationUrl(self):
        return self._github_verification_url

    @Property(bool, notify=changed)
    def githubAuthorizationReady(self):
        return bool(self._github_user_code and self._github_verification_url)

    @Property(int, notify=changed)
    def githubCodeSecondsRemaining(self):
        return max(0, int(self._github_code_expires_at - time.time() + 0.999))

    def _github_client_id(self):
        return self._github_client_id_override or str(self._config.get("github_client_id") or "").strip()

    @staticmethod
    def _iso_timestamp(value):
        try:
            text = str(value or "").strip().replace("Z", "+00:00")
            return datetime.fromisoformat(text).timestamp()
        except (TypeError, ValueError):
            return 0.0

    @Property(str, notify=changed)
    def uploadPath(self):
        return self._upload_inspection.path if self._upload_inspection else ""

    @Property(str, notify=changed)
    def uploadName(self):
        return self._upload_inspection.display_name if self._upload_inspection else "No JSON selected"

    @Property(str, notify=changed)
    def uploadPreviewUrl(self):
        return self._upload_inspection.preview_url if self._upload_inspection else ""

    @Property(int, notify=changed)
    def uploadShapeCount(self):
        return self._upload_inspection.shape_count if self._upload_inspection else 0

    @Property(str, notify=changed)
    def uploadSchemaLabel(self):
        return self._upload_inspection.schema_label if self._upload_inspection else ""

    @Property(bool, notify=changed)
    def uploadSchemaKnown(self):
        return bool(self._upload_inspection and self._upload_inspection.schema_known)

    @Property(str, notify=changed)
    def uploadSchemaWarning(self):
        return self._upload_inspection.schema_warning if self._upload_inspection else ""

    @Property(str, notify=changed)
    def uploadDetectedGamesText(self):
        if not self._upload_inspection:
            return ""
        return ", ".join(self._upload_inspection.detected_games)

    @Property(str, notify=changed)
    def uploadNormalizationNote(self):
        return self._upload_inspection.normalization_note if self._upload_inspection else ""

    @Property(bool, notify=changed)
    def uploadCompatibilityConfirmationRequired(self):
        return bool(self._upload_inspection and not self._upload_inspection.schema_known)

    @Property(str, notify=changed)
    def uploadStatus(self):
        return self._upload_status

    @Property(bool, notify=changed)
    def uploadReady(self):
        return bool(self._upload_inspection and self.authenticated and self.username)

    @Property(str, notify=changed)
    def downloadedPath(self):
        return self._downloaded_path

    def _submit(self, operation: str, function) -> None:
        if self._closed:
            return
        self._busy_count += 1
        self._error = ""
        self.changed.emit()
        future = self._executor.submit(function)

        def completed(result_future):
            if self._closed:
                return
            try:
                envelope = {"ok": True, "value": result_future.result()}
            except CommunityApiError as exc:
                envelope = {"ok": False, "status": exc.status, "code": exc.code, "message": exc.message}
            except Exception as exc:
                envelope = {"ok": False, "status": 0, "code": "local_error", "message": str(exc) or "The operation failed."}
            self._resultReady.emit(operation, envelope)

        future.add_done_callback(completed)

    def _submit_background(self, operation: str, function) -> None:
        if self._closed:
            return
        future = self._executor.submit(function)

        def completed(result_future):
            if self._closed:
                return
            try:
                envelope = {"ok": True, "value": result_future.result()}
            except CommunityApiError as exc:
                envelope = {"ok": False, "status": exc.status, "code": exc.code, "message": exc.message}
            except Exception as exc:
                envelope = {"ok": False, "status": 0, "code": "local_error", "message": str(exc) or "The operation failed."}
            self._resultReady.emit(operation, envelope)

        future.add_done_callback(completed)

    @Slot()
    def activate(self):
        if self._closed:
            return
        if self.demo:
            self._connected = True
            self._status = "Community demo catalog"
            self.changed.emit()
            return
        self._status = "Connecting to the community library..."
        self._submit("bootstrap", self._bootstrap)

    def _bootstrap(self):
        client = CommunityApiClient(self._base_url, self._token)
        health = client.json("health")
        config = client.json("config")
        session = {}
        expired = False
        if self._token:
            try:
                session = client.json("session", authenticated=True)
            except CommunityApiError as exc:
                if exc.status == 401:
                    client.token = ""
                    expired = True
                else:
                    raise
        # Featured is public metadata, including thumbnails for curated supporter
        # artwork. Full supporter assets and downloads remain entitlement-protected.
        catalog = client.json(self._catalog_path("featured"), authenticated=bool(client.token))
        return {"health": health, "config": config, "session": session, "expired": expired, "catalog": catalog}

    def _catalog_path(self, selected_scope=None):
        selected_scope = selected_scope or self._scope
        if selected_scope == "featured":
            return build_query("artworks", {
                "sort": "featured",
                "scope": "featured",
                "page": 1,
                "limit": FEATURED_ARTWORK_LIMIT,
            })
        classification = selected_scope if selected_scope in {"handmade", "toolmade"} else ""
        scope = "browse" if classification else selected_scope
        return build_query("artworks", {
            "search": self._search,
            "category": self._category,
            "game": self._game,
            "sort": self._sort,
            "scope": scope,
            "classification": classification,
            "creator": self._creator_filter,
            "page": self._page,
            "limit": 24,
        })

    def _clear_catalog(self):
        self._request_generation += 1
        self._rows = []
        self._artwork_model.replace([])
        self._page = 1
        self._page_count = 1
        self._total = 0
        self._selected_index = -1
        self._selected = {}
        self._selection_touched = False

    @Slot()
    def refresh(self):
        if self.demo:
            self._apply_demo_catalog()
            self.changed.emit()
            return
        if self._scope == "supporters" and not self.supporterAccess:
            self._clear_catalog()
            self._status = "Supporter vinyl sharing is available with verified supporter access."
            self.ensureSupporterEntitlement()
            self.changed.emit()
            return
        self._request_generation += 1
        generation = self._request_generation
        path = self._catalog_path()
        token = self._token
        self._status = "Refreshing community artwork..."
        self._submit(f"catalog:{generation}", lambda: CommunityApiClient(self._base_url, token).json(path, authenticated=bool(token)))

    @Slot(str)
    def setSearchQuery(self, value):
        value = str(value or "").strip()[:100]
        if value == self._search:
            return
        self._search = value
        self._creator_filter = ""
        self._page = 1
        self._selection_touched = False
        self.changed.emit()
        self._filter_timer.start()

    @Slot(str)
    def setCategory(self, value):
        value = str(value or "All")
        if value == self._category:
            return
        self._category = value
        self._page = 1
        self._selection_touched = False
        self.changed.emit()
        self.refresh()

    @Slot(str)
    def setGame(self, value):
        value = str(value or "All")
        if value == self._game:
            return
        self._game = value
        self._page = 1
        self._selection_touched = False
        self.changed.emit()
        self.refresh()

    @Slot(int)
    def setSortIndex(self, index):
        if not 0 <= index < len(SORT_VALUES) or SORT_VALUES[index] == self._sort:
            return
        self._sort = SORT_VALUES[index]
        self._page = 1
        self._selection_touched = False
        self.changed.emit()
        self.refresh()

    @Slot(int)
    def setScopeIndex(self, index):
        if not 0 <= index < len(SCOPE_VALUES):
            return
        if SCOPE_VALUES[index] in {"favorites", "following", "mine"} and not self.authenticated:
            self._error = "Sign in to use personal community views."
            self.changed.emit()
            return
        if SCOPE_VALUES[index] == self._scope:
            return
        self._scope = SCOPE_VALUES[index]
        self._creator_filter = ""
        self._page = 1
        self._selection_touched = False
        self.changed.emit()
        if self._scope == "supporters" and not self.supporterAccess:
            self._supporter_request_after = 0.0
        self.refresh()

    @Slot()
    def nextPage(self):
        if self._page < self._page_count:
            self._page += 1
            self._selection_touched = False
            self.changed.emit()
            self.refresh()

    @Slot()
    def previousPage(self):
        if self._page > 1:
            self._page -= 1
            self._selection_touched = False
            self.changed.emit()
            self.refresh()

    @Slot(int)
    def selectArtwork(self, index):
        if not 0 <= index < len(self._rows):
            return
        self._selected_index = index
        self._selected = dict(self._rows[index])
        self._selection_touched = True
        self.changed.emit()
        self._schedule_selected_supporter_preview()

    @Slot(int)
    def selectRelativeArtwork(self, offset):
        target = self._selected_index + int(offset)
        if 0 <= target < len(self._rows):
            self.selectArtwork(target)

    @Slot(str)
    def browseCreator(self, username):
        username = str(username or "").strip()
        if not username:
            return
        self._creator_filter = username
        self._scope = "browse"
        self._search = ""
        self._page = 1
        self._selection_touched = False
        self.changed.emit()
        self.refresh()

    @Slot()
    def clearCreatorFilter(self):
        if not self._creator_filter:
            return
        self._creator_filter = ""
        self._page = 1
        self._selection_touched = False
        self.changed.emit()
        self.refresh()

    @Slot()
    def connectAccount(self):
        provider = "local-test" if self.testAuthenticationAvailable and not self.githubAuthenticationAvailable else "github"
        self.connectAccountWith(provider)

    @Slot(str)
    def connectAccountWith(self, provider):
        if self.authenticated:
            return
        if self._authentication_in_progress:
            return
        provider = str(provider or "").strip().lower()
        if provider == "local-test":
            if not self.testAuthenticationAvailable:
                self._error = "Local test sign-in is disabled on this service."
                self.changed.emit()
                return
            installation = self._credentials.installation_id()
            self._authentication_in_progress = True
            self._authentication_provider = provider
            self._status = "Connecting a local community test account..."
            self._submit("auth", lambda: self._auth_test(installation))
            return
        if provider != "github":
            self._error = "Choose a supported community sign-in method."
            self.changed.emit()
            return
        client_id = self._github_client_id()
        if not re.fullmatch(r"[A-Za-z0-9]{16,128}", client_id):
            self._error = "Community sign-in is not configured on this service."
            self.changed.emit()
            return
        self._github_cancel.clear()
        self._authentication_in_progress = True
        self._authentication_provider = provider
        self._github_user_code = ""
        self._github_verification_url = ""
        self._github_code_expires_at = 0.0
        self._status = "Starting GitHub sign-in..."
        self._submit("auth", lambda: self._github_auth_flow(client_id))

    def _auth_test(self, installation):
        client = CommunityApiClient(self._base_url)
        result = client.json("auth/test", "POST", {
            "installation_id": installation,
            "display_name": os.environ.get("USERNAME", "Local KFPS Tester"),
        })
        client.token = str(result.get("token") or "")
        result["session"] = client.json("session", authenticated=True)
        return result

    def _github_auth_flow(self, client_id):
        device = _github_post_json(GITHUB_DEVICE_CODE_URL, {"client_id": client_id})
        device_code = str(device.get("device_code") or "")
        user_code = str(device.get("user_code") or "")
        verification_url = str(device.get("verification_uri") or "")
        try:
            expires_in = int(device.get("expires_in") or 0)
            interval = int(device.get("interval") or 0)
        except (TypeError, ValueError) as exc:
            raise CommunityApiError(502, "invalid_github_response", "GitHub returned invalid sign-in timing data.") from exc
        if (
            not 20 <= len(device_code) <= 256
            or not re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", user_code)
            or verification_url != GITHUB_VERIFICATION_URL
            or not 60 <= expires_in <= 1800
            or not 5 <= interval <= 60
        ):
            raise CommunityApiError(502, "invalid_github_response", "GitHub returned invalid device sign-in data.")
        self._githubDeviceReady.emit({
            "user_code": user_code,
            "verification_uri": verification_url,
            "expires_in": expires_in,
        })
        deadline = time.monotonic() + expires_in
        while time.monotonic() < deadline:
            if self._github_cancel.wait(interval):
                raise CommunityApiError(499, "github_auth_cancelled", "GitHub sign-in was cancelled.")
            token_result = _github_post_json(GITHUB_ACCESS_TOKEN_URL, {
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            })
            if token_result.get("access_token"):
                client = CommunityApiClient(self._base_url)
                result = client.json("auth/github", "POST", {"access_token": token_result["access_token"]})
                client.token = str(result.get("token") or "")
                result["session"] = client.json("session", authenticated=True)
                return result
            error = str(token_result.get("error") or "")
            if error == "slow_down":
                interval += 5
            elif error == "access_denied":
                raise CommunityApiError(401, "github_auth_denied", "GitHub sign-in was declined.")
            elif error in {"expired_token", "token_expired"}:
                raise CommunityApiError(401, "github_auth_expired", "The GitHub sign-in code expired. Start again.")
            elif error == "device_flow_disabled":
                raise CommunityApiError(503, "github_device_flow_disabled", "GitHub Device Flow is not enabled for this service.")
            elif error not in ("", "authorization_pending"):
                description = str(token_result.get("error_description") or "GitHub could not complete sign-in.")
                raise CommunityApiError(401, "github_auth_failed", description)
        raise CommunityApiError(401, "github_auth_expired", "GitHub sign-in expired. Start it again.")

    @Slot()
    def cancelAuthentication(self):
        if not self._authentication_in_progress:
            return
        self._github_cancel.set()
        self._status = "Cancelling GitHub sign-in..."
        self.changed.emit()

    @Slot()
    def copyGithubCode(self):
        if not self._github_user_code:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._github_user_code)
            self._status = "GitHub sign-in code copied."
            self.changed.emit()

    @Slot()
    def openGithubVerification(self):
        if self._github_verification_url != GITHUB_VERIFICATION_URL:
            return
        try:
            webbrowser.open(self._github_verification_url)
            self._status = "GitHub sign-in page opened."
        except Exception:
            self._error = "The GitHub sign-in page could not be opened."
        self.changed.emit()

    @Slot(str, str)
    def chooseUsername(self, value, confirmation):
        username = str(value or "").strip()
        confirmed = str(confirmation or "").strip()
        if not self._token:
            self._error = "Sign in before choosing a username."
            self.changed.emit()
            return
        if confirmed != username:
            self._error = "Confirm the exact username, including capitalization, before choosing it permanently."
            self.changed.emit()
            return
        self._submit("choose_username", lambda: CommunityApiClient(self._base_url, self._token).json(
            "profile/username", "POST",
            {"username": username, "confirm_username": confirmed}, authenticated=True
        ))

    @Slot(str, str)
    def updateProfile(self, bio, website):
        if not self.authenticated:
            return
        self._submit("update_profile", lambda: CommunityApiClient(self._base_url, self._token).json(
            "profile", "PATCH", {"bio": str(bio or ""), "website_url": str(website or "")}, authenticated=True
        ))

    @Slot()
    def refreshAccount(self):
        if self.authenticated and not self.demo:
            self._submit("session_refresh", lambda: CommunityApiClient(self._base_url, self._token).json(
                "session", authenticated=True
            ))

    @Slot()
    def ensureSupporterEntitlement(self):
        if self.demo or not self.authenticated or (self._local_supporter_state and self._local_supporter_state != "active"):
            return
        subject = str(self._session_user.get("id") or "").strip()
        if not subject:
            return
        now = time.time()
        verified_until = self._iso_timestamp(self._supporter.get("verified_until"))
        if self.supporterAccess and verified_until > now + 8 * 60:
            return
        if self._supporter_entitlement_pending or now < self._supporter_request_after:
            return
        self._supporter_entitlement_pending = True
        self._supporter_request_subject = subject
        self._supporter_request_after = now + 5 * 60
        self._supporter_status = "Verifying supporter Community access..."
        self.changed.emit()
        self.supporterEntitlementRequested.emit(subject)

    @Slot()
    def refreshSupporterEntitlement(self):
        self._supporter_request_after = 0.0
        self.ensureSupporterEntitlement()

    @Slot(object)
    def applySupporterEntitlement(self, result):
        if not isinstance(result, dict):
            return
        subject = str(result.get("subject") or "")
        if not subject or subject != str(self._session_user.get("id") or ""):
            return
        if self._local_supporter_state and self._local_supporter_state != "active":
            self._supporter_entitlement_pending = False
            self._clear_supporter_access()
            return
        self._supporter_entitlement_pending = False
        self._supporter_request_subject = ""
        if not result.get("ok"):
            self._supporter_status = str(
                result.get("message") or "An active supporter registration was not found on this device."
            )
            self.changed.emit()
            return
        entitlement = result.get("entitlement")
        if not isinstance(entitlement, dict):
            self._supporter_status = "Supporter Community verification returned an invalid response."
            self.changed.emit()
            return
        token = self._token
        self._supporter_status = "Confirming supporter Community access..."
        self._submit("supporter_verify", lambda: CommunityApiClient(self._base_url, token).json(
            "supporter/verify", "POST", {"entitlement": entitlement}, authenticated=True
        ))

    @staticmethod
    def _hard_inactive_supporter_state(state):
        return state in {"no_key", "invalid_key", "deactivated", "revoked", "duplicate", "not_eligible"}

    @Slot(str)
    @Slot(str, bool)
    def setLocalSupporterState(self, state, key_available=False):
        state = str(state or "").strip()
        previous = self._local_supporter_state
        self._local_supporter_state = state
        self._local_supporter_key_available = bool(key_available)
        if state == "active":
            if previous != state:
                self._supporter_request_after = 0.0
            self.ensureSupporterEntitlement()
        elif self._hard_inactive_supporter_state(state):
            self._clear_supporter_access()
        self.changed.emit()

    @Slot()
    def repairSupporterAccess(self):
        if self._local_supporter_key_available:
            self._supporter_status = "Checking the local supporter registration..."
            self.changed.emit()
            self.supporterRepairRequested.emit()

    def _clear_supporter_access(self):
        if self._supporter.get("active") or self._supporter.get("verified_until"):
            self._supporter_clear_required = True
        self._supporter = {"active": False, "verified_until": ""}
        self._supporter_entitlement_pending = False
        self._supporter_status = "Supporter Community access is not active on this device."
        if self._scope == "supporters":
            self._clear_catalog()
            self._status = "Supporter vinyl sharing is available with verified supporter access."
        now = time.time()
        if (
            not self._supporter_clear_required or self.demo or not self.authenticated or self._supporter_clear_inflight
            or now < self._supporter_clear_after
        ):
            return
        self._supporter_clear_inflight = True
        self._supporter_clear_after = now + 60
        token = self._token
        self._submit("supporter_clear", lambda: CommunityApiClient(self._base_url, token).json(
            "supporter/verify", "DELETE", authenticated=True
        ))

    @Slot()
    def _supporter_tick(self):
        access = self.supporterAccess
        if self._scope == "supporters" and not access:
            self._supporter_status = "Supporter Community access expired and needs to be verified again."
            self._clear_catalog()
        self.changed.emit()
        if self._hard_inactive_supporter_state(self._local_supporter_state):
            self._clear_supporter_access()
        else:
            self.ensureSupporterEntitlement()

    @Slot()
    def signOut(self):
        token = self._token
        self._credentials.clear_token()
        self._token = ""
        self._client.token = ""
        self._session_user = {}
        self._session_stats = {}
        self._supporter = {}
        self._supporter_entitlement_pending = False
        self._supporter_request_subject = ""
        self._supporter_clear_inflight = False
        self._supporter_clear_required = False
        self._supporter_status = "Connect a supporter registration to unlock this catalog."
        self._scope = "featured"
        self._selection_touched = False
        self._status = "Signed out. Browsing remains available."
        self.changed.emit()
        if token and not self.demo:
            self._executor.submit(lambda: CommunityApiClient(self._base_url, token).json(
                "session", "DELETE", authenticated=True
            ))
        self.refresh()

    @Slot()
    def chooseUploadJson(self):
        path = self.desktop.chooseJson()
        if not path:
            return
        self._prepare_upload_json(path)

    @Slot(str)
    def selectUploadJson(self, value):
        self._prepare_upload_json(value)

    def _prepare_upload_json(self, value):
        self._upload_request_generation += 1
        generation = self._upload_request_generation
        try:
            path = Path(str(value or "").strip()).expanduser().resolve(strict=True)
        except (OSError, RuntimeError):
            path = None
        if not path or not path.is_file() or path.suffix.casefold() != ".json":
            self._upload_inspection = None
            self._error = "Choose an existing JSON file to prepare for upload."
            self._upload_status = self._error
            self.changed.emit()
            return
        self._upload_inspection = None
        self._error = ""
        self._upload_status = "Validating JSON and rendering its community preview..."
        self.changed.emit()
        self._submit(
            f"inspect_upload:{generation}",
            lambda: inspect_upload(path, self.paths.runtime_root),
        )

    @Slot(str, str, str, str, str, str, bool, bool, bool)
    def submitUpload(
        self, title, description, category, tags_text, classification, license,
        supporter_only, confirm_rights, confirm_compatibility,
    ):
        inspection = self._upload_inspection
        if not inspection:
            self._error = "Choose and validate a JSON before uploading."
            self.changed.emit()
            return
        if not self.uploadReady:
            self._error = "Sign in and choose your permanent username before uploading."
            self.changed.emit()
            return
        if supporter_only and not self.supporterAccess:
            self._error = "Verify an active supporter registration before publishing supporter artwork."
            self.refreshSupporterEntitlement()
            self.changed.emit()
            return
        payload = self._upload_payload(
            title, description, category, tags_text, classification, license,
            supporter_only, confirm_rights, confirm_compatibility,
        )
        self._upload_status = "Uploading for server validation and publication..."
        self._submit("upload", lambda: CommunityApiClient(self._base_url, self._token).json(
            "artworks", "POST", payload, authenticated=True
        ))

    @Slot(str, str, str, str, str, str, bool, bool, bool, str)
    def submitRevision(
        self, title, description, category, tags_text, classification, license,
        supporter_only, confirm_rights, confirm_compatibility, change_note,
    ):
        if not self._upload_inspection:
            self._error = "Choose and validate the replacement JSON first."
            self.changed.emit()
            return
        if not self.selectedOwned:
            self._error = "Select one of your own uploads before submitting a revision."
            self.changed.emit()
            return
        payload = self._upload_payload(
            title, description, category, tags_text, classification, license,
            supporter_only, confirm_rights, confirm_compatibility,
        )
        payload["change_note"] = str(change_note or "").strip()
        artwork_id = urllib.parse.quote(str(self._selected.get("id") or ""))
        self._upload_status = "Uploading the revision for server validation and publication..."
        self._submit("revision", lambda: CommunityApiClient(self._base_url, self._token).json(
            f"artworks/{artwork_id}/revisions", "POST", payload, authenticated=True
        ))

    def _upload_payload(
        self, title, description, category, tags_text, classification, license,
        supporter_only, confirm_rights, confirm_compatibility,
    ):
        inspection = self._upload_inspection
        if not inspection:
            return {}
        return {
            "client_version": self._app_version,
            "title": str(title or inspection.display_name),
            "description": str(description or ""),
            "category": str(category or "Other"),
            "classification": str(classification or ""),
            "supporter_only": bool(supporter_only),
            "tags": [item.strip() for item in str(tags_text or "").split(",") if item.strip()],
            "license": str(license or "kfps-community-share-v1"),
            "confirm_rights": bool(confirm_rights),
            "confirm_compatibility": bool(confirm_compatibility),
            "design": inspection.payload,
            "preview_base64": base64.b64encode(inspection.preview_bytes).decode("ascii"),
            "thumbnail_base64": base64.b64encode(inspection.thumbnail_bytes).decode("ascii"),
        }

    @Slot(str)
    def updateSelectedTags(self, tags_text):
        if not self.selectedMetadataEditable:
            self._error = "Open Profile > My Uploads and select one of your uploads before editing tags."
            self.changed.emit()
            return
        artwork_id = urllib.parse.quote(str(self._selected.get("id") or ""))
        payload = {
            "tags": [item.strip() for item in str(tags_text or "").split(",") if item.strip()],
        }
        self._submit("metadata", lambda: CommunityApiClient(self._base_url, self._token).json(
            f"artworks/{artwork_id}", "PATCH", payload, authenticated=True
        ))

    @Slot()
    def favoriteSelected(self):
        if not self.hasSelection or not self.authenticated:
            self._error = "Sign in to save community favorites."
            self.changed.emit()
            return
        artwork_id = str(self._selected["id"])
        favorite = not bool(self._selected.get("favorited"))
        self._submit("favorite", lambda: CommunityApiClient(self._base_url, self._token).json(
            f"artworks/{urllib.parse.quote(artwork_id)}/favorite", "POST", {"favorite": favorite}, authenticated=True
        ))

    @Slot()
    def followSelectedCreator(self):
        creator = str(self._selected.get("creatorName") or self._profile.get("username") or "")
        if not creator or not self.authenticated:
            self._error = "Sign in to follow creators."
            self.changed.emit()
            return
        followed = bool(self._selected.get("creatorFollowed") or self._profile.get("followed"))
        self._submit("follow", lambda: CommunityApiClient(self._base_url, self._token).json(
            f"creators/{urllib.parse.quote(creator)}/follow", "POST", {"follow": not followed}, authenticated=True
        ))

    @Slot(str)
    def loadCreator(self, username):
        username = str(username or "").strip()
        if not username:
            return
        token = self._token
        self._submit("creator", lambda: CommunityApiClient(self._base_url, token).json(
            f"creators/{urllib.parse.quote(username)}", authenticated=bool(token)
        ))

    @Slot(str, str)
    def reportSelected(self, reason, details):
        if not self.hasSelection or not self.authenticated:
            self._error = "Sign in before reporting community content."
            self.changed.emit()
            return
        artwork_id = str(self._selected["id"])
        self._submit("report", lambda: CommunityApiClient(self._base_url, self._token).json(
            f"artworks/{urllib.parse.quote(artwork_id)}/report", "POST",
            {"reason": str(reason or "other"), "details": str(details or "")}, authenticated=True
        ))

    @Slot()
    def removeSelectedUpload(self):
        if not self.hasSelection or not self.authenticated:
            return
        artwork_id = str(self._selected["id"])
        self._submit("remove", lambda: CommunityApiClient(self._base_url, self._token).json(
            f"artworks/{urllib.parse.quote(artwork_id)}", "DELETE", authenticated=True
        ))

    @Slot()
    def downloadSelected(self):
        if not self.hasSelection:
            return
        if self.selectedSupporterLocked:
            self._error = "Verified supporter access is required to download this artwork."
            self.changed.emit()
            return
        if not self.authenticated:
            self._error = "Sign in before downloading community artwork."
            self.changed.emit()
            return
        selected = dict(self._selected)
        token = self._token
        self._status = "Downloading and validating the selected community JSON..."
        self._submit("download", lambda: self._download_artwork(selected, token))

    def _download_artwork(self, selected, token):
        client = CommunityApiClient(self._base_url, token)
        raw, _headers = client.binary(str(selected.get("downloadUrl") or ""), authenticated=True)
        validate_download(raw, str(selected.get("contentSha256") or ""))
        creator = community_file_part(selected.get("creatorName"), "Unknown")
        title = community_file_part(selected.get("title"), "Community Artwork")
        folder = self.paths.library_root / "Community" / creator / title
        target = folder / f"{title}.json"
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(raw).hexdigest():
            target = folder / f"{title}.{str(selected.get('id') or '')[:8]}.json"
        folder.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, raw)
        manifest = {
            "format": "kfps.community.download.v1",
            "community_id": selected.get("id"),
            "title": selected.get("title"),
            "creator": selected.get("creatorName"),
            "category": selected.get("category"),
            "games": str(selected.get("gamesText") or "").split(", "),
            "source_schema": selected.get("schemaId"),
            "schema_label": selected.get("schemaLabel"),
            "schema_known": selected.get("schemaKnown"),
            "schema_warning": selected.get("schemaWarning"),
            "license": selected.get("license"),
            "supporter_only": bool(selected.get("supporterOnly")),
            "shape_count": selected.get("shapeCount"),
            "content_sha256": selected.get("contentSha256"),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_write(target.with_suffix(".community.manifest.json"), json.dumps(manifest, indent=2).encode("utf-8"))
        try:
            preview_path = str(selected.get("_previewAssetUrl") or selected.get("previewUrl") or "")
            preview, _preview_headers = client.binary(preview_path, authenticated=bool(token), maximum=2 * 1024 * 1024)
            expected_preview = str(selected.get("previewSha256") or "")
            if preview.startswith(b"\x89PNG\r\n\x1a\n") and (not expected_preview or hashlib.sha256(preview).hexdigest() == expected_preview):
                self._atomic_write(target.with_suffix(".png"), preview)
        except Exception:
            pass
        return {"path": str(target.resolve()), "title": selected.get("title")}

    @staticmethod
    def _atomic_write(path: Path, data: bytes):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    @Slot()
    def openDownloadedFolder(self):
        if self._downloaded_path:
            self.desktop.openFolder(str(Path(self._downloaded_path).parent))
        else:
            self.desktop.openFolder(str(self.paths.library_root / "Community"))

    @Slot()
    def clearError(self):
        self._error = ""
        self.changed.emit()

    def _schedule_private_previews(self):
        if not self._token:
            return
        for row in self._rows:
            if row.get("supporterOnly"):
                if not self.supporterAccess:
                    continue
                artwork_id = str(row.get("id") or "")
                digest = str(row.get("thumbnailSha256") or "")
                memory_key = f"thumbnail:{digest or artwork_id}"
                if memory_key in self._supporter_asset_memory:
                    self._set_row_memory_asset(artwork_id, digest, "thumbnail", self._supporter_asset_memory[memory_key])
                    continue
                key = f"supporter_thumbnail:{artwork_id}:{digest}"
                if key in self._private_preview_inflight:
                    continue
                self._private_preview_inflight.add(key)
                asset_url = str(row.get("_thumbnailAssetUrl") or "")
                token = self._token
                self._submit_background(
                    key,
                    lambda artwork_id=artwork_id, digest=digest, asset_url=asset_url, token=token:
                        self._fetch_supporter_asset(artwork_id, digest, asset_url, token, "thumbnail"),
                )
                continue
            if row.get("status") == "published" or not row.get("previewUrl"):
                continue
            artwork_id = str(row.get("id") or "")
            digest = str(row.get("previewSha256") or "")
            cache_name = digest if re.fullmatch(r"[a-fA-F0-9]{64}", digest) else hashlib.sha256(artwork_id.encode("utf-8")).hexdigest()
            target = self._root / "private-previews" / f"{cache_name}.png"
            try:
                raw = target.read_bytes()
                if raw.startswith(b"\x89PNG\r\n\x1a\n") and (not digest or hashlib.sha256(raw).hexdigest() == digest):
                    self._set_row_preview(artwork_id, digest, target)
                    continue
            except Exception:
                pass
            key = f"{artwork_id}:{digest}"
            if key in self._private_preview_inflight:
                continue
            self._private_preview_inflight.add(key)
            preview_url = str(row.get("previewUrl") or "")
            token = self._token
            self._submit_background(
                f"private_preview:{key}",
                lambda artwork_id=artwork_id, digest=digest, preview_url=preview_url, token=token, target=target:
                    self._fetch_private_preview(artwork_id, digest, preview_url, token, target),
            )
        self._schedule_selected_supporter_preview()

    def _schedule_selected_supporter_preview(self):
        if not self._token or not self.supporterAccess or not self._selected.get("supporterOnly"):
            return
        artwork_id = str(self._selected.get("id") or "")
        digest = str(self._selected.get("previewSha256") or "")
        memory_key = f"preview:{digest or artwork_id}"
        if memory_key in self._supporter_asset_memory:
            self._set_row_memory_asset(artwork_id, digest, "preview", self._supporter_asset_memory[memory_key])
            return
        key = f"supporter_preview:{artwork_id}:{digest}"
        if key in self._private_preview_inflight:
            return
        self._private_preview_inflight.add(key)
        asset_url = str(self._selected.get("_previewAssetUrl") or "")
        token = self._token
        self._submit_background(
            key,
            lambda: self._fetch_supporter_asset(artwork_id, digest, asset_url, token, "preview"),
        )

    def _fetch_supporter_asset(self, artwork_id, digest, asset_url, token, kind):
        maximum = 2 * 1024 * 1024 if kind == "thumbnail" else 8 * 1024 * 1024
        raw, _headers = CommunityApiClient(self._base_url, token).binary(
            asset_url, authenticated=True, maximum=maximum,
        )
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise CommunityApiError(502, "invalid_preview", "The supporter artwork preview is not a PNG.")
        if digest and hashlib.sha256(raw).hexdigest() != digest:
            raise CommunityApiError(502, "preview_checksum_mismatch", "The supporter artwork preview checksum does not match.")
        data_url = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        return {"id": artwork_id, "digest": digest, "kind": kind, "data_url": data_url}

    def _set_row_memory_asset(self, artwork_id, digest, kind, data_url):
        memory_key = f"{kind}:{digest or artwork_id}"
        self._supporter_asset_memory[memory_key] = data_url
        while len(self._supporter_asset_memory) > 64:
            self._supporter_asset_memory.pop(next(iter(self._supporter_asset_memory)))
        role = "thumbnailUrl" if kind == "thumbnail" else "previewUrl"
        for index, row in enumerate(self._rows):
            expected = row.get("thumbnailSha256") if kind == "thumbnail" else row.get("previewSha256")
            if row.get("id") == artwork_id and (not digest or expected == digest):
                row[role] = data_url
                self._artwork_model.set_row_value(index, role, data_url)
                if self._selected.get("id") == artwork_id:
                    self._selected[role] = data_url
                    if kind == "thumbnail" and not self._selected.get("previewUrl"):
                        self._selected["previewUrl"] = data_url
                return

    def _fetch_private_preview(self, artwork_id, digest, preview_url, token, target):
        raw, _headers = CommunityApiClient(self._base_url, token).binary(preview_url, authenticated=True, maximum=2 * 1024 * 1024)
        if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
            raise CommunityApiError(502, "invalid_preview", "The private artwork preview is not a PNG.")
        if digest and hashlib.sha256(raw).hexdigest() != digest:
            raise CommunityApiError(502, "preview_checksum_mismatch", "The private artwork preview checksum does not match.")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(target, raw)
        return {"id": artwork_id, "digest": digest, "path": str(target)}

    def _set_row_preview(self, artwork_id, digest, target):
        for index, row in enumerate(self._rows):
            if row.get("id") == artwork_id and (not digest or row.get("previewSha256") == digest):
                url = file_url(target)
                row["previewUrl"] = url
                row["thumbnailUrl"] = url
                self._artwork_model.set_row_value(index, "previewUrl", url)
                self._artwork_model.set_row_value(index, "thumbnailUrl", url)
                if self._selected.get("id") == artwork_id:
                    self._selected["previewUrl"] = url
                return

    @Slot()
    def close(self):
        if self._closed:
            return
        self._closed = True
        self._filter_timer.stop()
        self._supporter_timer.stop()
        self._authentication_timer.stop()
        self._github_cancel.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _finish_authentication(self):
        self._authentication_in_progress = False
        self._authentication_provider = ""
        self._github_user_code = ""
        self._github_verification_url = ""
        self._github_code_expires_at = 0.0
        self._authentication_timer.stop()
        self._github_cancel.clear()

    @Slot(str, object)
    def _apply_result(self, operation, envelope):
        background_asset = operation.startswith(("private_preview:", "supporter_thumbnail:", "supporter_preview:"))
        if not background_asset:
            self._busy_count = max(0, self._busy_count - 1)
        upload_inspection = operation.startswith("inspect_upload:")
        if upload_inspection:
            try:
                generation = int(operation.split(":", 1)[1])
            except (IndexError, ValueError):
                generation = -1
            if generation != self._upload_request_generation:
                self.changed.emit()
                return
        if not envelope.get("ok"):
            code = str(envelope.get("code") or "request_failed")
            message = str(envelope.get("message") or "The community request failed.")
            if background_asset:
                self._private_preview_inflight.discard(operation)
                self._private_preview_inflight.discard(operation.split(":", 1)[1])
                self.log.append(f"Community private preview failed: {code}: {message}", "warning")
                return
            if operation == "supporter_clear":
                self._supporter_clear_inflight = False
                self._supporter_status = "Restricted access is disabled locally; server confirmation will retry."
                self.log.append(f"Community supporter clear failed: {code}: {message}", "warning")
                self.changed.emit()
                return
            if operation == "auth":
                self._finish_authentication()
                if code == "github_auth_cancelled":
                    self._status = "GitHub sign-in cancelled."
                    self._error = ""
                    self.changed.emit()
                    return
            if int(envelope.get("status") or 0) == 401 and code in {"invalid_session", "session_expired"}:
                self._credentials.clear_token()
                self._token = ""
                self._client.token = ""
                self._session_user = {}
                self._session_stats = {}
                self._supporter = {}
            self._error = message
            self._status = "Community request failed."
            if upload_inspection:
                self._upload_inspection = None
                self._upload_status = message
            self.log.append(f"Community {operation.split(':', 1)[0]} failed: {code}: {message}", "warning")
            self.changed.emit()
            return

        value = envelope.get("value") or {}
        if operation == "bootstrap":
            self._connected = True
            self._config = dict(value.get("config") or self._config)
            if value.get("expired"):
                self._credentials.clear_token()
                self._token = ""
                self._client.token = ""
            self._apply_session(value.get("session") or {})
            self._status = "Community library connected."
            if self._scope == "featured":
                self._apply_catalog(value.get("catalog") or {})
                self._schedule_private_previews()
            else:
                self._clear_catalog()
                self.refresh()
        elif operation.startswith("catalog:"):
            generation = int(operation.split(":", 1)[1])
            if generation == self._request_generation:
                self._connected = True
                self._apply_catalog(value)
                self._schedule_private_previews()
                self._status = "Community catalog is up to date."
        elif operation == "auth":
            token = str(value.get("token") or "")
            if not self._credentials.save_token(token):
                self._error = "Windows could not securely store the community session."
            self._token = token
            self._client.token = token
            self._apply_session(value.get("session") or {})
            self._status = "Community account connected."
            self._finish_authentication()
            self.refresh()
        elif operation == "choose_username":
            user = dict(value.get("user") or {})
            self._session_user.update(user)
            self._status = f"Community username locked as @{self.username}."
        elif operation == "update_profile":
            self._session_user.update(dict(value.get("user") or {}))
            self._status = "Creator profile updated."
        elif operation == "session_refresh":
            self._apply_session(value)
            self._status = "Community account is up to date."
        elif operation == "supporter_verify":
            self._supporter = dict(value.get("supporter") or {})
            self._supporter_entitlement_pending = False
            self._supporter_status = (
                "Supporter Community access is verified."
                if self.supporterAccess else "Supporter Community verification expired."
            )
            self._status = "Supporter Community access updated."
            if self.supporterAccess and self._scope in {"supporters", "featured"}:
                self.refresh()
        elif operation == "supporter_clear":
            self._supporter_clear_inflight = False
            self._supporter_clear_required = False
            self._supporter = dict(value.get("supporter") or {"active": False, "verified_until": ""})
            self._supporter_status = "Supporter Community access is not active on this device."
            self._status = "Supporter Community access cleared."
        elif upload_inspection:
            self._upload_inspection = value
            self._upload_status = (
                f"Ready: {value.shape_count} shapes, {value.size_bytes / (1024 * 1024):.2f} MB. "
                f"Detected {value.schema_label}."
            )
        elif operation == "upload":
            artwork = dict(value.get("artwork") or {})
            self._upload_status = (
                "Published after local and server file validation."
                if artwork.get("status") == "published"
                else "Uploaded for manual moderation."
            )
            self._status = self._upload_status
            self._scope = "mine"
            self._page = 1
            self._selected = {"id": str(artwork.get("id") or "")}
            self._selection_touched = bool(self._selected["id"])
            self.refresh()
        elif operation == "revision":
            revision = int(value.get("revision") or 0)
            self._upload_status = (
                f"Revision {revision} published after file validation."
                if value.get("status") == "published"
                else f"Revision {revision} uploaded for manual moderation."
            )
            self._status = self._upload_status
            self._scope = "mine"
            self._creator_filter = ""
            self._page = 1
            self._selected = {"id": str(value.get("artwork_id") or "")}
            self._selection_touched = bool(self._selected["id"])
            self.refresh()
        elif operation == "metadata":
            artwork = dict(value.get("artwork") or {})
            self._status = "Upload tags updated."
            self._selected = {"id": str(artwork.get("id") or self._selected.get("id") or "")}
            self._selection_touched = bool(self._selected["id"])
            self.refresh()
        elif operation == "favorite":
            self._update_selected("favorited", bool(value.get("favorited")))
            self._update_selected("favorites", int(value.get("favorites") or 0))
            self._status = "Favorite updated."
        elif operation == "follow":
            self._update_selected("creatorFollowed", bool(value.get("followed")))
            self._update_selected("creatorFollowers", int(value.get("followers") or 0))
            self._profile["followed"] = bool(value.get("followed"))
            self._profile["followers"] = int(value.get("followers") or 0)
            self._status = "Creator follow updated."
        elif operation == "creator":
            self._profile = dict(value.get("creator") or {})
            self._status = "Creator profile loaded."
        elif operation == "report":
            self._status = "Report submitted privately and highlighted for moderation."
        elif operation == "remove":
            self._status = "Your artwork was removed from the active catalog."
            self._selection_touched = False
            self.refresh()
        elif operation == "download":
            self._downloaded_path = str(value.get("path") or "")
            self._status = f"Downloaded {value.get('title') or 'community artwork'} to the KFPS Library."
            self.log.append(f"Community JSON downloaded: {self._downloaded_path}")
            if self.jsons is not None:
                try:
                    self.jsons.setSource(3)
                    self.jsons.refresh()
                except Exception:
                    pass
        elif operation.startswith("private_preview:"):
            self._private_preview_inflight.discard(operation.split(":", 1)[1])
            self._set_row_preview(str(value.get("id") or ""), str(value.get("digest") or ""), Path(str(value.get("path") or "")))
        elif operation.startswith(("supporter_thumbnail:", "supporter_preview:")):
            self._private_preview_inflight.discard(operation)
            self._set_row_memory_asset(
                str(value.get("id") or ""), str(value.get("digest") or ""),
                str(value.get("kind") or "thumbnail"), str(value.get("data_url") or ""),
            )
        self.changed.emit()

    @Slot(object)
    def _apply_github_device(self, payload):
        self._github_user_code = str(payload.get("user_code") or "")
        self._github_verification_url = str(payload.get("verification_uri") or "")
        self._github_code_expires_at = time.time() + int(payload.get("expires_in") or 0)
        self._authentication_timer.start()
        self._status = f"Enter code {self._github_user_code} in the GitHub page."
        self.changed.emit()
        self.openGithubVerification()

    def _apply_session(self, payload):
        self._session_user = dict(payload.get("user") or {})
        self._session_stats = dict(payload.get("stats") or {})
        self._supporter = dict(payload.get("supporter") or {})
        self._supporter_status = (
            "Supporter Community access is verified."
            if self.supporterAccess else "Connect an active supporter registration to unlock this catalog."
        )
        if self._hard_inactive_supporter_state(self._local_supporter_state):
            QTimer.singleShot(0, self._clear_supporter_access)
        else:
            QTimer.singleShot(0, self.ensureSupporterEntitlement)

    def _apply_catalog(self, payload):
        rows = [self._normalize_artwork(item) for item in payload.get("items", []) if isinstance(item, dict)]
        if self._scope == "featured":
            rows = [row for row in rows if row.get("featured")][:FEATURED_ARTWORK_LIMIT]
        elif self._scope in {"browse", "handmade", "toolmade", "supporters", "following"}:
            rows = [row for row in rows if not row.get("featured")]
        selected_id = str(self._selected.get("id") or "") if self._selection_touched else ""
        self._rows = rows
        self._artwork_model.replace(rows)
        if self._scope == "featured":
            self._page = 1
            self._page_count = 1
            self._total = len(rows)
        else:
            self._page = max(1, int(payload.get("page") or 1))
            self._page_count = max(1, int(payload.get("page_count") or 1))
            self._total = max(0, int(payload.get("total") or 0))
        match = next((index for index, row in enumerate(rows) if row["id"] == selected_id), -1)
        self._selected_index = match if match >= 0 else (0 if rows else -1)
        self._selected = dict(rows[self._selected_index]) if self._selected_index >= 0 else {}
        self._write_cache(payload)

    def _normalize_artwork(self, item):
        creator = dict(item.get("creator") or {})
        supporter_only = bool(item.get("supporter_only"))
        featured = bool(item.get("featured"))
        preview_digest = str(item.get("preview_sha256") or "")
        thumbnail_digest = str(item.get("thumbnail_sha256") or preview_digest)
        preview_asset_url = _versioned_asset_url(
            self._client.url(str(item.get("preview_url") or "")), preview_digest,
        )
        thumbnail_asset_url = _versioned_asset_url(
            self._client.url(str(item.get("thumbnail_url") or item.get("preview_url") or "")), thumbnail_digest,
        )
        return {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or "Untitled"),
            "description": str(item.get("description") or ""),
            "category": str(item.get("category") or "Other"),
            "classification": str(item.get("classification") or "toolmade"),
            "classificationLabel": "Handmade" if str(item.get("classification") or "toolmade") == "handmade" else "Toolmade",
            "tagsText": ", ".join(str(value) for value in item.get("tags", [])),
            "gamesText": ", ".join(str(value) for value in item.get("games", [])),
            "license": str(item.get("license") or "kfps-community-share-v1"),
            "schemaId": str(item.get("source_schema") or "legacy-kfps"),
            "schemaLabel": str(item.get("schema_label") or "KFPS-compatible JSON"),
            "schemaKnown": bool(item.get("schema_known", True)),
            "schemaWarning": str(item.get("schema_warning") or ""),
            "shapeCount": int(item.get("shape_count") or 0),
            "groupCount": int(item.get("group_count") or 0),
            "usesMasks": bool(item.get("uses_masks")),
            "status": str(item.get("status") or "published"),
            "statusLabel": str(item.get("status") or "published").replace("_", " ").title(),
            "rejectionReason": str(item.get("rejection_reason") or ""),
            "featured": featured,
            "supporterOnly": supporter_only,
            "supporterLabel": "Supporters" if supporter_only else "Everyone",
            "revision": int(item.get("current_revision") or 1),
            "downloads": int(item.get("downloads") or 0),
            "favorites": int(item.get("favorites") or 0),
            "favorited": bool(item.get("favorited")),
            "createdAt": str(item.get("created_at") or ""),
            "updatedAt": str(item.get("updated_at") or ""),
            "publishedAt": str(item.get("published_at") or ""),
            "previewUrl": thumbnail_asset_url if supporter_only and featured else ("" if supporter_only else preview_asset_url),
            "thumbnailUrl": thumbnail_asset_url if supporter_only and featured else ("" if supporter_only else thumbnail_asset_url),
            "downloadUrl": self._client.url(str(item.get("download_url") or "")),
            "contentSha256": str(item.get("content_sha256") or ""),
            "previewSha256": preview_digest,
            "thumbnailSha256": thumbnail_digest,
            "creatorName": str(creator.get("username") or "Unknown"),
            "creatorAvatar": str(creator.get("avatar_url") or ""),
            "creatorBio": str(creator.get("bio") or ""),
            "creatorFollowers": int(creator.get("follower_count") or 0),
            "creatorFollowed": bool(creator.get("followed")),
            "_previewAssetUrl": preview_asset_url,
            "_thumbnailAssetUrl": thumbnail_asset_url,
        }

    def _update_selected(self, key, value):
        self._selected[key] = value
        if 0 <= self._selected_index < len(self._rows):
            self._rows[self._selected_index][key] = value
            self._artwork_model.set_row_value(self._selected_index, key, value)

    def _load_cache(self):
        try:
            payload = json.loads(self._cache_file.read_text(encoding="utf-8"))
            if (payload.get("version") == 5
                    and payload.get("endpoint") == self._endpoint_key
                    and payload.get("scope") == self._scope
                    and isinstance(payload.get("catalog"), dict)):
                self._apply_catalog(payload["catalog"])
                self._status = "Showing cached community artwork while connecting."
        except Exception:
            pass

    def _write_cache(self, catalog):
        items = catalog.get("items", []) if isinstance(catalog, dict) else []
        if (
            self._scope not in {"featured", "browse", "handmade", "toolmade"}
            or not isinstance(items, list)
            or (
                self._scope != "featured"
                and any(isinstance(item, dict) and item.get("supporter_only") for item in items)
            )
        ):
            return
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            target = self._catalog_cache_file(self._scope)
            payload = {
                "version": 5,
                "endpoint": self._endpoint_key,
                "scope": self._scope,
                "saved_at": time.time(),
                "catalog": catalog,
            }
            self._atomic_write(target, json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        except Exception:
            pass

    def _catalog_cache_file(self, scope):
        safe_scope = str(scope or "featured").replace("_", "-")
        return self._root / f"catalog-cache.{self._endpoint_key}.{safe_scope}.v5.json"

    def _load_demo_rows(self):
        self._token = "demo-session"
        self._client.token = self._token
        self._session_user = {
            "id": "11111111-1111-4111-8111-111111111111",
            "username": "DemoCreator",
            "bio": "Local demonstration profile for layout and interaction checks.",
            "website_url": "https://example.com/kfps-demo",
            "avatar_url": "",
        }
        self._session_stats = {
            "artwork_count": 6,
            "favorite_count": 14,
            "following_count": 5,
            "follower_count": 22,
        }
        self._supporter = {
            "active": True,
            "verified_until": datetime.fromtimestamp(time.time() + 3600, timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self._supporter_status = "Supporter Community access is verified."
        rows = []
        for index in range(10):
            rows.append({
                role: ({
                    "id": f"demo-{index}", "title": f"Community Artwork {index + 1:02d}",
                    "description": "A cached community browser demonstration.", "category": "Original Artwork",
                    "classification": "handmade" if index % 2 == 0 else "toolmade",
                    "classificationLabel": "Handmade" if index % 2 == 0 else "Toolmade",
                    "tagsText": "demo, artwork", "gamesText": "FH6, FM8", "license": "Community Share",
                    "schemaId": "kfps-primitives", "schemaLabel": "KFPS primitive geometry",
                    "schemaKnown": index != 8,
                    "schemaWarning": "" if index != 8 else "Compatibility has not been verified for this format.",
                    "shapeCount": 420 + index * 83, "status": "published", "statusLabel": "Published",
                    "featured": index < 2, "revision": 1, "downloads": 80 - index * 3,
                    "favorites": 18 - index, "creatorName": "GalleryCreator",
                    "usesMasks": index in {0, 3, 6},
                    "supporterOnly": index in {1, 4, 7},
                    "supporterLabel": "Supporters" if index in {1, 4, 7} else "Everyone",
                }).get(role, False if role in {"favorited", "creatorFollowed"} else 0 if role in {"groupCount", "creatorFollowers"} else "")
                for role in ARTWORK_ROLES
            })
        self._demo_all_rows = rows
        self._apply_demo_catalog()

    def _apply_demo_catalog(self):
        rows = [dict(row) for row in self._demo_all_rows]
        if self._scope == "featured":
            rows = [row for row in rows if row.get("featured")][:FEATURED_ARTWORK_LIMIT]
        elif self._scope == "supporters":
            rows = [row for row in rows if row.get("supporterOnly") and not row.get("featured")]
        else:
            rows = [row for row in rows if not row.get("supporterOnly") and not row.get("featured")]
            if self._scope in {"handmade", "toolmade"}:
                rows = [row for row in rows if row.get("classification") == self._scope]
        if self._scope != "featured" and self._search:
            needle = self._search.casefold()
            rows = [
                row for row in rows
                if needle in " ".join((
                    str(row.get("title") or ""),
                    str(row.get("creatorName") or ""),
                    str(row.get("tagsText") or ""),
                )).casefold()
            ]
        self._rows = rows
        self._artwork_model.replace(rows)
        self._page = 1
        self._page_count = 1
        self._total = len(rows)
        self._selected_index = 0 if rows else -1
        self._selected = dict(rows[0]) if rows else {}
