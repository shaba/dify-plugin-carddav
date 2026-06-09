from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from carddav_client.api import make_session, search_contacts
from carddav_client.contacts import format_contact_list
from tools._common import error_message


class SearchContactsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        base_url = str(self.runtime.credentials.get("base_url") or "").strip()
        username = str(self.runtime.credentials.get("username") or "").strip()
        password = str(self.runtime.credentials.get("password") or "")
        query = str(tool_parameters.get("query") or "").strip()
        addressbook = str(tool_parameters.get("addressbook") or "").strip() or None

        if not base_url:
            yield self.create_text_message("Error: the plugin base_url is not configured")
            return
        if not query:
            yield self.create_text_message("Error: the 'query' parameter is required")
            return

        try:
            session = make_session(username, password)
            book, contacts = search_contacts(session, base_url, query, addressbook)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        yield self.create_text_message(
            format_contact_list(contacts, f'Matches for "{query}" in "{book.name}"'))
        yield self.create_json_message({
            "addressbook": book.name,
            "query": query,
            "count": len(contacts),
            "contacts": [c.to_dict() for c in contacts],
        })
