"""WebDAV/CardDAV protocol: request bodies, multistatus parsing, discovery, queries.

Discovery flow per RFC 6352:
  current-user-principal -> addressbook-home-set -> PROPFIND address books
  -> REPORT addressbook-query / addressbook-multiget for vCards.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lxml import etree

from .errors import CardDavError, DiscoveryError
from .http import (
    DavSession,
    check_status,
    resolve_href,
    resolve_href_same_origin,
    same_origin,
)

DAV_NS = "DAV:"
CARDDAV_NS = "urn:ietf:params:xml:ns:carddav"
NSMAP = {"d": DAV_NS, "card": CARDDAV_NS}


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


# --- request bodies -------------------------------------------------------

PROPFIND_CURRENT_USER_PRINCIPAL = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:">'
    "<d:prop><d:current-user-principal/></d:prop>"
    "</d:propfind>"
)

PROPFIND_ADDRESSBOOK_HOME = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><card:addressbook-home-set/></d:prop>"
    "</d:propfind>"
)

PROPFIND_ADDRESSBOOKS = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
    "<d:prop>"
    "<d:resourcetype/>"
    "<d:displayname/>"
    "<card:addressbook-description/>"
    "</d:prop>"
    "</d:propfind>"
)

REPORT_ADDRESSBOOK_QUERY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<card:addressbook-query xmlns:d="DAV:" '
    'xmlns:card="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><d:getetag/><card:address-data/></d:prop>"
    # RFC 6352 §10.3: <filter> is REQUIRED. A prop-filter with a single
    # <is-not-defined/> negated by test="anyof" matches every card (a card
    # either has UID or it does not), giving a portable "fetch all" query that
    # strict servers (SOGo, Cyrus, Apple) accept instead of rejecting with 400.
    '<card:filter test="anyof">'
    '<card:prop-filter name="UID"/>'
    '<card:prop-filter name="UID"><card:is-not-defined/></card:prop-filter>'
    "</card:filter>"
    "</card:addressbook-query>"
)


# --- parsing helpers ------------------------------------------------------

# Hardened parser: the multistatus body comes from a remote (potentially hostile
# or MITM'd) CardDAV server. Disable entity resolution, DTD loading and network
# access to neutralise internal-entity expansion ("billion laughs") and XXE.
_XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    load_dtd=False,
    dtd_validation=False,
    huge_tree=False,
)


def _parse_xml(text: str) -> etree._Element:
    root = etree.fromstring(text.encode("utf-8"), parser=_XML_PARSER)
    if root.getroottree().docinfo.doctype:
        raise DiscoveryError("CardDAV response contains a DOCTYPE; refusing to parse")
    return root


def _text(el: etree._Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


@dataclass
class AddressBook:
    href: str
    display_name: str
    description: str = ""

    @property
    def name(self) -> str:
        return self.display_name or self.href.rstrip("/").rsplit("/", 1)[-1]


@dataclass
class RawCard:
    href: str
    etag: str
    vcard: str


def _responses(root: etree._Element) -> list[etree._Element]:
    return root.findall(_q(DAV_NS, "response"))


def _href_of(response: etree._Element) -> str:
    return _text(response.find(_q(DAV_NS, "href")))


def _status_is_2xx(status: str) -> bool:
    """True if a DAV status line carries a 2xx code.

    The status line is the raw HTTP status-line ("HTTP/1.1 200 OK"). RFC 7540
    drops the reason phrase, so HTTP/2 servers may send "HTTP/2 200" with no
    trailing token — a substring match on " 200 " would miss it. Parse the
    numeric code from the tokens instead.
    """
    for token in status.split():
        if token.isdigit() and 200 <= int(token) <= 299:
            return True
    return False


def _ok_propstat_prop(response: etree._Element) -> etree._Element | None:
    """Return the <prop> of the 2xx propstat, or the first prop as a fallback.

    The first-prop fallback is intentional: some servers return a single propstat
    with no (or a non-2xx) status line, and we still want to read whatever props
    they provided rather than dropping the response entirely.
    """
    fallback = None
    for propstat in response.findall(_q(DAV_NS, "propstat")):
        prop = propstat.find(_q(DAV_NS, "prop"))
        if prop is None:
            continue
        if fallback is None:
            fallback = prop
        if _status_is_2xx(_text(propstat.find(_q(DAV_NS, "status")))):
            return prop
    return fallback


def parse_principal(text: str) -> str:
    root = _parse_xml(text)
    for response in _responses(root):
        prop = _ok_propstat_prop(response)
        if prop is None:
            continue
        cup = prop.find(_q(DAV_NS, "current-user-principal"))
        if cup is not None:
            href = _text(cup.find(_q(DAV_NS, "href")))
            if href:
                return href
    raise DiscoveryError("current-user-principal not found in PROPFIND response")


def parse_addressbook_home(text: str) -> str:
    root = _parse_xml(text)
    for response in _responses(root):
        prop = _ok_propstat_prop(response)
        if prop is None:
            continue
        home = prop.find(_q(CARDDAV_NS, "addressbook-home-set"))
        if home is not None:
            href = _text(home.find(_q(DAV_NS, "href")))
            if href:
                return href
    raise DiscoveryError("addressbook-home-set not found in PROPFIND response")


def parse_addressbooks(text: str, base_url: str) -> list[AddressBook]:
    root = _parse_xml(text)
    books: list[AddressBook] = []
    for response in _responses(root):
        href = _href_of(response)
        prop = _ok_propstat_prop(response)
        if prop is None:
            continue
        resourcetype = prop.find(_q(DAV_NS, "resourcetype"))
        is_book = (
            resourcetype is not None
            and resourcetype.find(_q(CARDDAV_NS, "addressbook")) is not None
        )
        if not is_book:
            continue
        resolved = resolve_href(base_url, href)
        if not same_origin(base_url, resolved):
            # A book href pointing off-origin would be REPORTed/PUT to with the
            # user's credentials; skip it (see resolve_href_same_origin).
            continue
        books.append(
            AddressBook(
                href=resolved,
                display_name=_text(prop.find(_q(DAV_NS, "displayname"))),
                description=_text(prop.find(_q(CARDDAV_NS, "addressbook-description"))),
            )
        )
    return books


def parse_address_data(text: str, base_url: str) -> list[RawCard]:
    root = _parse_xml(text)
    cards: list[RawCard] = []
    for response in _responses(root):
        href = _href_of(response)
        prop = _ok_propstat_prop(response)
        if prop is None:
            continue
        data = prop.find(_q(CARDDAV_NS, "address-data"))
        if data is None or not (data.text or "").strip():
            continue
        cards.append(
            RawCard(
                href=resolve_href(base_url, href),
                etag=_text(prop.find(_q(DAV_NS, "getetag"))),
                vcard=data.text.strip(),
            )
        )
    return cards


# --- network operations (use the injected DavSession) ---------------------

def discover_addressbook_home(session: DavSession, base_url: str) -> str | None:
    """Resolve the address book home collection via the RFC 6352 principal chain.

    Returns the home collection URL, or ``None`` if the server does not expose
    ``current-user-principal``/``addressbook-home-set`` at ``base_url`` (common
    when the user already pointed us at an account/home URL, e.g. Radicale).
    Callers should then treat ``base_url`` itself as the home collection.
    """
    resp = session.request(
        "PROPFIND",
        base_url,
        body=PROPFIND_CURRENT_USER_PRINCIPAL,
        headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
    )
    check_status(resp, expected=(207,))
    try:
        principal = resolve_href_same_origin(base_url, parse_principal(resp.text))
    except DiscoveryError:
        return None

    resp = session.request(
        "PROPFIND",
        principal,
        body=PROPFIND_ADDRESSBOOK_HOME,
        headers={"Depth": "0", "Content-Type": "application/xml; charset=utf-8"},
    )
    check_status(resp, expected=(207,))
    try:
        return resolve_href_same_origin(base_url, parse_addressbook_home(resp.text))
    except DiscoveryError:
        return None


def _propfind_addressbooks(
    session: DavSession, collection_url: str, base_url: str
) -> list[AddressBook]:
    resp = session.request(
        "PROPFIND",
        collection_url,
        body=PROPFIND_ADDRESSBOOKS,
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    check_status(resp, expected=(207,))
    return parse_addressbooks(resp.text, base_url)


def list_addressbooks(session: DavSession, base_url: str) -> list[AddressBook]:
    """Discover address books, with a fallback for servers that skip the
    RFC 6352 principal chain (e.g. Radicale account URLs).

    Primary path: current-user-principal -> addressbook-home-set -> PROPFIND
    Depth:1 on the home. Fallback: if principal/home discovery yields nothing,
    or yields no address books, PROPFIND ``base_url`` directly and detect
    ``card:addressbook`` collections there.
    """
    home = discover_addressbook_home(session, base_url)
    if home is not None:
        books = _propfind_addressbooks(session, home, base_url)
        if books:
            return books
    if home != base_url:
        return _propfind_addressbooks(session, base_url, base_url)
    return []


def query_address_book(session: DavSession, addressbook_url: str) -> list[RawCard]:
    """REPORT addressbook-query: fetch every vCard in an address book collection.

    The filter is a match-all (see ``REPORT_ADDRESSBOOK_QUERY``); searching is
    done client-side. This is simple and server-agnostic but pulls the whole
    collection, so very large address books will be slow and memory-heavy.
    """
    resp = session.request(
        "REPORT",
        addressbook_url,
        body=REPORT_ADDRESSBOOK_QUERY,
        headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
    )
    check_status(resp, expected=(207,))
    return parse_address_data(resp.text, addressbook_url)


def put_vcard(
    session: DavSession, contact_url: str, vcard: str, *, if_none_match: bool = True
) -> str:
    """PUT a vCard to a (new) contact URL. Returns the contact URL on success."""
    headers: dict[str, str] = {"Content-Type": "text/vcard; charset=utf-8"}
    if if_none_match:
        headers["If-None-Match"] = "*"
    resp = session.request("PUT", contact_url, body=vcard, headers=headers)
    if resp.status_code == 412:
        # If-None-Match:* precondition failed -> a card already lives here.
        raise CardDavError(
            "a contact with this UID already exists at the target URL"
        )
    check_status(resp, expected=(200, 201, 204))
    # Some servers rewrite the path / assign their own UID and report the real
    # location via the Location header; prefer it over the requested URL.
    location = resp.headers.get("Location") or resp.headers.get("location")
    if location:
        return resolve_href(contact_url, location)
    return contact_url


def find_addressbook(
    books: list[AddressBook], selector: str | None
) -> AddressBook:
    """Pick an address book by name/href substring, or the first one if no selector."""
    if not books:
        raise DiscoveryError("no address books found on the CardDAV server")
    if not selector:
        return books[0]
    needle = selector.strip().lower()
    # Prefer a display-name match; only fall back to href matching when no book
    # name matches. On Nextcloud every href contains "addressbooks", so matching
    # href first would let a generic selector silently pick the wrong book.
    for book in books:
        if needle in book.name.lower():
            return book
    for book in books:
        if needle in book.href.lower():
            return book
    raise DiscoveryError(
        f'address book "{selector}" not found '
        f"(available: {', '.join(b.name for b in books)})"
    )


def addressbook_to_dict(book: AddressBook) -> dict[str, Any]:
    return {"name": book.name, "href": book.href, "description": book.description}
