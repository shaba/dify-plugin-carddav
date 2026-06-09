from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from carddav_client.api import get_contacts, make_session
from carddav_client.contacts import format_contact_list
from tools._common import error_message


class ListContactsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        base_url = str(self.runtime.credentials.get("base_url") or "").strip()
        username = str(self.runtime.credentials.get("username") or "").strip()
        password = str(self.runtime.credentials.get("password") or "")
        addressbook = str(tool_parameters.get("addressbook") or "").strip() or None

        if not base_url:
            yield self.create_text_message("Error: the plugin base_url is not configured")
            return

        try:
            session = make_session(username, password)
            book, contacts = get_contacts(session, base_url, addressbook)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        yield self.create_text_message(
            format_contact_list(contacts, f'Contacts in "{book.name}"'))
        yield self.create_json_message({
            "addressbook": book.name,
            "count": len(contacts),
            "contacts": [c.to_dict() for c in contacts],
        })
