from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from .errors import CardDavError

# Matches a top-level (column 0) ``version:`` line in manifest.yaml.
_VERSION_RE = re.compile(r"^version:\s*(\S+)", re.MULTILINE)


def _manifest_version() -> str:
    """Read the plugin version from manifest.yaml as the single source of truth.

    Derived at import time so the User-Agent always tracks the manifest version
    instead of a hardcoded literal that silently drifts. Falls back to
    ``"unknown"`` if the manifest is missing or unreadable.
    """
    manifest = Path(__file__).resolve().parent.parent / "manifest.yaml"
    try:
        match = _VERSION_RE.search(manifest.read_text(encoding="utf-8"))
    except OSError:
        return "unknown"
    return match.group(1) if match else "unknown"


DEFAULT_USER_AGENT = f"dify-plugin-carddav/{_manifest_version()}"


@dataclass
class DavResponse:
    status_code: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class DavSession(Protocol):
    """Minimal DAV transport. Implementations issue an arbitrary WebDAV method and
    return a :class:`DavResponse`. Injected so the client is testable without network."""

    def request(
        self,
        method: str,
        url: str,
        *,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> DavResponse: ...


class RequestsDavSession:
    """Default :class:`DavSession` backed by ``requests`` with HTTP Basic auth."""

    def __init__(
        self,
        username: str | None,
        password: str | None,
        *,
        timeout: int = 30,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._auth = (username or "", password or "") if (username or password) else None
        self._timeout = timeout
        self._user_agent = user_agent

    def request(
        self,
        method: str,
        url: str,
        *,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> DavResponse:
        merged = {"User-Agent": self._user_agent}
        if headers:
            merged.update(headers)
        data = body.encode("utf-8") if body is not None else None
        resp = requests.request(
            method,
            url,
            data=data,
            headers=merged,
            auth=self._auth,
            timeout=self._timeout,
            # Do not auto-follow 3xx: a hostile server could redirect a
            # credentialed request to an internal/off-origin host (SSRF / leak).
            allow_redirects=False,
        )
        return DavResponse(
            status_code=resp.status_code,
            text=resp.text,
            headers={k: v for k, v in resp.headers.items()},
        )


def check_status(resp: DavResponse, *, expected: tuple[int, ...]) -> None:
    if resp.status_code not in expected:
        raise CardDavError(
            f"CardDAV server returned HTTP {resp.status_code} "
            f"(expected {', '.join(str(c) for c in expected)})"
        )


def resolve_href(base_url: str, href: str) -> str:
    """Resolve an href from a multistatus response against the request URL.

    Hrefs are usually absolute paths (``/remote.php/dav/...``); occasionally full URLs.
    """
    href = href.strip()
    if not href:
        return base_url
    if urlsplit(href).scheme:
        return href
    if href.startswith("/"):
        # Absolute-path href ("/remote.php/dav/..."): keep base scheme+host,
        # replace the whole path.
        parts = urlsplit(base_url)
        return urlunsplit((parts.scheme, parts.netloc, "", "", "")) + href
    # Relative href: resolve against the full base URL.
    return urljoin(base_url, href)


def same_origin(base_url: str, url: str) -> bool:
    """True if ``url`` has the same scheme and host:port as ``base_url``."""
    a, b = urlsplit(base_url), urlsplit(url)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)


def resolve_href_same_origin(base_url: str, href: str) -> str:
    """Resolve ``href`` and reject cross-origin results.

    Used for credentialed discovery follow-ups (principal, addressbook-home):
    the href is supplied by the remote server and is then re-requested with the
    user's Basic-auth credentials. A hostile or MITM'd server could return an
    absolute URL pointing at an internal host or downgrade https->http, leaking
    the password (SSRF / credential forwarding). Constrain the next hop to the
    same scheme+host as the URL we were configured to talk to.
    """
    resolved = resolve_href(base_url, href)
    if not same_origin(base_url, resolved):
        raise CardDavError(
            "CardDAV discovery returned a cross-origin href "
            f"({resolved!r}); refusing to send credentials off-origin"
        )
    return resolved
