from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from carddav_client.api import get_contact, make_session
from carddav_client.contacts import format_contact_full
from tools._common import error_message


class GetContactTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        base_url = str(self.runtime.credentials.get("base_url") or "").strip()
        username = str(self.runtime.credentials.get("username") or "").strip()
        password = str(self.runtime.credentials.get("password") or "")
        identifier = str(tool_parameters.get("identifier") or "").strip()
        addressbook = str(tool_parameters.get("addressbook") or "").strip() or None

        if not base_url:
            yield self.create_text_message("Error: the plugin base_url is not configured")
            return
        if not identifier:
            yield self.create_text_message("Error: the 'identifier' parameter is required")
            return

        try:
            session = make_session(username, password)
            book, contact, candidates = get_contact(
                session, base_url, identifier, addressbook)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        if contact is None:
            # Distinguish "nothing matched" from "ambiguous": get_contact already
            # computed the substring candidates, so reuse them instead of issuing
            # a second full REPORT against the address book.
            if candidates:
                names = ", ".join(c.full_name or "(no name)" for c in candidates)
                yield self.create_text_message(
                    f'"{identifier}" is ambiguous in "{book.name}" — '
                    f"{len(candidates)} contacts match: {names}. "
                    "Please refine the identifier.")
            else:
                yield self.create_text_message(
                    f'No contact matched "{identifier}" in "{book.name}".')
            yield self.create_json_message({
                "addressbook": book.name,
                "found": False,
                "candidates": [c.full_name for c in candidates],
            })
            return

        yield self.create_text_message(format_contact_full(contact))
        yield self.create_json_message({
            "addressbook": book.name,
            "found": True,
            "contact": contact.to_dict(),
        })
