from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from carddav_client.api import get_addressbooks, make_session
from carddav_client.errors import redact_credentials


class CardDavProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        base_url = str(credentials.get("base_url") or "").strip()
        username = str(credentials.get("username") or "").strip()
        password = str(credentials.get("password") or "")
        if not base_url:
            raise ToolProviderCredentialValidationError(
                "base_url is required (e.g. https://example.com/remote.php/dav/)")
        if not username:
            raise ToolProviderCredentialValidationError("username is required")
        if not password:
            raise ToolProviderCredentialValidationError("password is required")
        try:
            session = make_session(username, password, timeout=15)
            get_addressbooks(session, base_url)
        except Exception as exc:  # noqa: BLE001
            safe_url = redact_credentials(base_url)
            raise ToolProviderCredentialValidationError(
                f"CardDAV is not reachable / address books not discoverable "
                f"at {safe_url}: {redact_credentials(exc)}") from exc
