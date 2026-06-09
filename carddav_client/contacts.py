"""vCard parsing, building and compact English formatting (via vobject).

We chose ``vobject`` over ``vcard``: ``vcard`` is a strict validator/linter aimed at
checking conformance, while ``vobject`` is a forgiving reader/writer for vCard 3.0/4.0
that round-trips real-world cards from Nextcloud/Radicale and lets us emit new ones.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

import vobject

from .dav import RawCard

PRODID = "-//dify-plugin-carddav//EN"


@dataclass
class Contact:
    uid: str = ""
    full_name: str = ""
    emails: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    org: str = ""
    title: str = ""
    href: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "full_name": self.full_name,
            "emails": self.emails,
            "phones": self.phones,
            "org": self.org,
            "title": self.title,
            "href": self.href,
        }


def _values(component: Any, name: str) -> list[str]:
    out: list[str] = []
    for child in component.contents.get(name, []):
        value = child.value
        if isinstance(value, (list, tuple)):
            value = " ".join(str(v) for v in value if str(v).strip())
        text = str(value).strip()
        if text:
            out.append(text)
    return out


def parse_vcard(text: str, *, href: str = "") -> Contact:
    card = vobject.readOne(text)
    full_name = ""
    if "fn" in card.contents:
        full_name = str(card.fn.value).strip()
    org = ""
    if "org" in card.contents:
        org_val = card.org.value
        if isinstance(org_val, (list, tuple)):
            org = "; ".join(str(v) for v in org_val if str(v).strip())
        else:
            org = str(org_val).strip()
    title = ""
    if "title" in card.contents:
        title = str(card.title.value).strip()
    uid = ""
    if "uid" in card.contents:
        uid = str(card.uid.value).strip()
    return Contact(
        uid=uid,
        full_name=full_name,
        emails=_values(card, "email"),
        phones=_values(card, "tel"),
        org=org,
        title=title,
        href=href,
    )


def parse_raw_card(raw: RawCard) -> Contact:
    return parse_vcard(raw.vcard, href=raw.href)


def parse_cards(raws: list[RawCard]) -> list[Contact]:
    contacts: list[Contact] = []
    for raw in raws:
        try:
            contacts.append(parse_raw_card(raw))
        except Exception:  # noqa: BLE001 — skip a single malformed card, keep the rest
            continue
    return contacts


def build_vcard(
    full_name: str,
    *,
    emails: list[str] | None = None,
    phones: list[str] | None = None,
    org: str = "",
    title: str = "",
    uid: str | None = None,
) -> tuple[str, str]:
    """Build a vCard 3.0. Returns ``(uid, serialized_vcard)``."""
    full_name = full_name.strip()
    if not full_name:
        raise ValueError("full_name is required to create a contact")
    card = vobject.vCard()
    card_uid = (uid or str(uuid.uuid4())).strip()
    card.add("prodid").value = PRODID
    card.add("uid").value = card_uid
    card.add("fn").value = full_name

    # Best-effort structured name (N): vCard 3.0 sorts/dedups on N, but we only
    # have a free-form FN. given=first token, family=last token; middle tokens
    # and non-Western name orders are not represented. FN remains authoritative.
    parts = full_name.split()
    given = parts[0] if parts else full_name
    family = parts[-1] if len(parts) > 1 else ""
    card.add("n").value = vobject.vcard.Name(family=family, given=given)

    # REV (revision timestamp) helps sync clients with conflict resolution.
    card.add("rev").value = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for email in emails or []:
        email = email.strip()
        if not email:
            continue
        entry = card.add("email")
        entry.value = email
        entry.type_param = "INTERNET"
    for phone in phones or []:
        phone = phone.strip()
        if not phone:
            continue
        entry = card.add("tel")
        entry.value = phone
        entry.type_param = "VOICE"
    if org.strip():
        card.add("org").value = [org.strip()]
    if title.strip():
        card.add("title").value = title.strip()

    return card_uid, card.serialize()


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def matches(contact: Contact, query: str) -> bool:
    needle = query.strip().lower()
    if not needle:
        return True
    haystacks = [
        contact.full_name,
        contact.org,
        contact.title,
        *contact.emails,
        *contact.phones,
    ]
    if any(needle in h.lower() for h in haystacks if h):
        return True
    # Phone numbers vary in formatting (spaces, dashes, "+"); if the query looks
    # like a phone fragment, compare on digits only so "5550143" finds
    # "+1-202-555-0143".
    needle_digits = _digits(needle)
    if needle_digits:
        return any(needle_digits in _digits(p) for p in contact.phones)
    return False


# --- compact English formatting -------------------------------------------

def format_contact_line(contact: Contact) -> str:
    line = f"- {contact.full_name or '(no name)'}"
    extras: list[str] = []
    if contact.org:
        extras.append(contact.org)
    if contact.emails:
        extras.append(contact.emails[0])
    if contact.phones:
        extras.append(contact.phones[0])
    if extras:
        line += " — " + ", ".join(extras)
    return line


def format_contact_full(contact: Contact) -> str:
    lines = [contact.full_name or "(no name)"]
    if contact.org or contact.title:
        org_line = " / ".join(x for x in (contact.title, contact.org) if x)
        lines.append(f"Org: {org_line}")
    if contact.emails:
        lines.append("Emails: " + ", ".join(contact.emails))
    if contact.phones:
        lines.append("Phones: " + ", ".join(contact.phones))
    if contact.uid:
        lines.append(f"UID: {contact.uid}")
    return "\n".join(lines)


def format_contact_list(
    contacts: list[Contact], header: str, *, limit: int | None = None
) -> str:
    if not contacts:
        return f"{header}: none found."
    shown = contacts if limit is None else contacts[:limit]
    out = [f"{header}: {len(contacts)} contact(s)"]
    if len(shown) < len(contacts):
        out[0] += f" (showing {len(shown)})"
    out.extend(format_contact_line(c) for c in shown)
    return "\n".join(out)
