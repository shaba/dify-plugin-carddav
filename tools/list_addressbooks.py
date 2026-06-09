from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from carddav_client.api import get_addressbooks, make_session
from carddav_client.dav import addressbook_to_dict
from tools._common import error_message


class ListAddressbooksTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        base_url = str(self.runtime.credentials.get("base_url") or "").strip()
        username = str(self.runtime.credentials.get("username") or "").strip()
        password = str(self.runtime.credentials.get("password") or "")

        if not base_url:
            yield self.create_text_message("Error: the plugin base_url is not configured")
            return

        try:
            session = make_session(username, password)
            books = get_addressbooks(session, base_url)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        if not books:
            yield self.create_text_message("No address books found on the CardDAV server.")
            yield self.create_json_message({"count": 0, "addressbooks": []})
            return

        lines = [f"Address books: {len(books)}"]
        for book in books:
            line = f"- {book.name}"
            if book.description:
                line += f" — {book.description}"
            lines.append(line)
        yield self.create_text_message("\n".join(lines))
        yield self.create_json_message({
            "count": len(books),
            "addressbooks": [addressbook_to_dict(b) for b in books],
        })
