from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from carddav_client.api import create_contact, make_session
from carddav_client.contacts import format_contact_full
from tools._common import error_message


def _split(value: str) -> list[str]:
    # Split on commas and newlines only. Do NOT split on ';' — a phone number
    # may legitimately contain it (e.g. an extension "+1-202-555-0143;ext=12").
    parts: list[str] = []
    for chunk in str(value or "").replace("\n", ",").split(","):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return parts


class CreateContactTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        base_url = str(self.runtime.credentials.get("base_url") or "").strip()
        username = str(self.runtime.credentials.get("username") or "").strip()
        password = str(self.runtime.credentials.get("password") or "")
        full_name = str(tool_parameters.get("full_name") or "").strip()
        emails = _split(tool_parameters.get("emails", ""))
        phones = _split(tool_parameters.get("phones", ""))
        org = str(tool_parameters.get("org") or "").strip()
        title = str(tool_parameters.get("title") or "").strip()
        addressbook = str(tool_parameters.get("addressbook") or "").strip() or None

        if not base_url:
            yield self.create_text_message("Error: the plugin base_url is not configured")
            return
        if not full_name:
            yield self.create_text_message("Error: the 'full_name' parameter is required")
            return

        try:
            session = make_session(username, password)
            book, contact = create_contact(
                session, base_url,
                full_name=full_name, emails=emails, phones=phones,
                org=org, title=title, addressbook=addressbook,
            )
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        yield self.create_text_message(
            f'Created contact in "{book.name}":\n' + format_contact_full(contact))
        yield self.create_json_message({
            "addressbook": book.name,
            "created": True,
            "contact": contact.to_dict(),
        })
