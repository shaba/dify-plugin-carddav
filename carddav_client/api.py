"""High-level operations used by the Dify tools, built on the injectable DavSession.

Each function takes a :class:`DavSession`, so tests can drive them with a fake session
that returns canned multistatus XML; production code passes a ``RequestsDavSession``.
"""
from __future__ import annotations

from .contacts import Contact, build_vcard, matches, parse_cards
from .dav import (
    AddressBook,
    find_addressbook,
    list_addressbooks,
    put_vcard,
    query_address_book,
)
from .http import DavSession, RequestsDavSession


def make_session(
    username: str | None, password: str | None, *, timeout: int = 30
) -> RequestsDavSession:
    return RequestsDavSession(username, password, timeout=timeout)


def get_addressbooks(session: DavSession, base_url: str) -> list[AddressBook]:
    return list_addressbooks(session, base_url)


def get_contacts(
    session: DavSession, base_url: str, addressbook: str | None = None
) -> tuple[AddressBook, list[Contact]]:
    books = list_addressbooks(session, base_url)
    book = find_addressbook(books, addressbook)
    cards = query_address_book(session, book.href)
    return book, parse_cards(cards)


def search_contacts(
    session: DavSession, base_url: str, query: str, addressbook: str | None = None
) -> tuple[AddressBook, list[Contact]]:
    book, contacts = get_contacts(session, base_url, addressbook)
    return book, [c for c in contacts if matches(c, query)]


def get_contact(
    session: DavSession, base_url: str, identifier: str, addressbook: str | None = None
) -> tuple[AddressBook, Contact | None, list[Contact]]:
    """Find a single contact by exact UID, exact full name, or substring match.

    Returns ``(book, contact, candidates)``. ``contact`` is the resolved match
    or ``None``; ``candidates`` is the list of substring matches that was
    considered. Callers get the candidates back so they can report an ambiguous
    identifier (multiple matches) without issuing a second full REPORT.
    """
    book, contacts = get_contacts(session, base_url, addressbook)
    needle = identifier.strip()
    low = needle.lower()
    candidates = [c for c in contacts if matches(c, needle)]
    for contact in contacts:  # exact UID or full name first
        if contact.uid == needle or contact.full_name.lower() == low:
            return book, contact, candidates
    if len(candidates) == 1:
        return book, candidates[0], candidates
    if candidates:
        # prefer a name match over an org/email-only match when ambiguous
        named = [c for c in candidates if low in c.full_name.lower()]
        if len(named) == 1:
            return book, named[0], candidates
    return book, None, candidates


def create_contact(
    session: DavSession,
    base_url: str,
    *,
    full_name: str,
    emails: list[str] | None = None,
    phones: list[str] | None = None,
    org: str = "",
    title: str = "",
    addressbook: str | None = None,
) -> tuple[AddressBook, Contact]:
    books = list_addressbooks(session, base_url)
    book = find_addressbook(books, addressbook)
    uid, vcard = build_vcard(
        full_name, emails=emails, phones=phones, org=org, title=title
    )
    contact_url = book.href.rstrip("/") + f"/{uid}.vcf"
    # put_vcard returns the server-reported location if it differs (Location
    # header), otherwise the requested URL.
    final_url = put_vcard(session, contact_url, vcard)
    contact = Contact(
        uid=uid,
        full_name=full_name.strip(),
        emails=[e.strip() for e in (emails or []) if e.strip()],
        phones=[p.strip() for p in (phones or []) if p.strip()],
        org=org.strip(),
        title=title.strip(),
        href=final_url,
    )
    return book, contact
