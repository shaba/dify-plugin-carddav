import pytest

from carddav_client.dav import (
    REPORT_ADDRESSBOOK_QUERY,
    discover_addressbook_home,
    find_addressbook,
    list_addressbooks,
    parse_addressbook_home,
    parse_addressbooks,
    parse_address_data,
    parse_principal,
    put_vcard,
    query_address_book,
)
from carddav_client.errors import CardDavError, DiscoveryError
from carddav_client.http import (
    DavResponse,
    check_status,
    resolve_href,
    resolve_href_same_origin,
)
from tests.conftest import load_fixture


def test_resolve_href_absolute_path():
    assert resolve_href("https://example.com/remote.php/dav/", "/foo/bar") == \
        "https://example.com/foo/bar"


def test_resolve_href_full_url():
    assert resolve_href("https://example.com/x/", "https://other.com/y") == \
        "https://other.com/y"


def test_parse_principal():
    href = parse_principal(load_fixture("principal.xml"))
    assert href == "/remote.php/dav/principals/users/alice/"


def test_parse_principal_missing():
    with pytest.raises(DiscoveryError):
        parse_principal('<d:multistatus xmlns:d="DAV:"></d:multistatus>')


def test_parse_addressbook_home():
    href = parse_addressbook_home(load_fixture("home.xml"))
    assert href == "/remote.php/dav/addressbooks/users/alice/"


def test_parse_addressbooks_filters_non_addressbook(base_url):
    books = parse_addressbooks(load_fixture("addressbooks.xml"), base_url)
    names = [b.name for b in books]
    assert names == ["Contacts", "Work"]  # the bare collection is skipped
    assert books[0].href == \
        "https://example.com/remote.php/dav/addressbooks/users/alice/contacts/"
    assert books[0].description == "Default address book"


def test_parse_address_data_skips_empty(base_url):
    cards = parse_address_data(load_fixture("query.xml"), base_url)
    assert len(cards) == 3  # broken card is still raw text here; filtered at parse_cards
    assert cards[0].etag == '"etag-john-1"'
    assert cards[0].vcard.startswith("BEGIN:VCARD")


def test_discover_addressbook_home(session, base_url):
    home = discover_addressbook_home(session, base_url)
    assert home == \
        "https://example.com/remote.php/dav/addressbooks/users/alice/"


def test_list_addressbooks(session, base_url):
    books = list_addressbooks(session, base_url)
    assert [b.name for b in books] == ["Contacts", "Work"]


def test_query_address_book(session, base_url):
    cards = query_address_book(session, base_url + "addressbooks/users/alice/contacts/")
    assert len(cards) == 3


def test_find_addressbook_default_and_selector(base_url):
    books = parse_addressbooks(load_fixture("addressbooks.xml"), base_url)
    assert find_addressbook(books, None).name == "Contacts"
    assert find_addressbook(books, "work").name == "Work"
    with pytest.raises(DiscoveryError):
        find_addressbook(books, "nope")
    with pytest.raises(DiscoveryError):
        find_addressbook([], None)


def test_find_addressbook_prefers_name_over_href(base_url):
    books = parse_addressbooks(load_fixture("addressbooks.xml"), base_url)
    # "contacts" appears in the Work book's href path too, but the name match on
    # the Contacts book must win.
    assert find_addressbook(books, "contacts").name == "Contacts"


def test_report_query_includes_required_filter():
    # RFC 6352 §10.3: addressbook-query MUST carry a <filter>.
    assert "card:filter" in REPORT_ADDRESSBOOK_QUERY


def test_check_status_raises_on_unexpected():
    with pytest.raises(CardDavError):
        check_status(DavResponse(400, ""), expected=(207,))


def test_put_vcard_412_collision(session):
    session.put_status = 412
    with pytest.raises(CardDavError, match="already exists"):
        put_vcard(session, "https://example.com/book/x.vcf", "BEGIN:VCARD")


def test_put_vcard_returns_location_header():
    class LocSession:
        def request(self, method, url, *, body=None, headers=None):
            return DavResponse(201, "", {"Location": "/dav/book/server-uid.vcf"})

    out = put_vcard(LocSession(), "https://example.com/book/x.vcf", "BEGIN:VCARD")
    assert out == "https://example.com/dav/book/server-uid.vcf"


def test_parse_xml_rejects_doctype():
    payload = (
        '<?xml version="1.0"?>'
        '<!DOCTYPE x [<!ENTITY a "boom">]>'
        '<d:multistatus xmlns:d="DAV:"><x>&a;</x></d:multistatus>'
    )
    with pytest.raises(DiscoveryError):
        parse_principal(payload)


def test_parse_addressbooks_http2_status_line(base_url):
    """HTTP/2 status lines drop the reason phrase ("HTTP/2 200"); the success
    propstat must still be recognised even when a 404 propstat comes first."""
    body = (
        '<d:multistatus xmlns:d="DAV:" '
        'xmlns:card="urn:ietf:params:xml:ns:carddav">'
        "<d:response>"
        "<d:href>/dav/addressbooks/users/alice/contacts/</d:href>"
        "<d:propstat>"
        "<d:prop><card:addressbook-description/></d:prop>"
        "<d:status>HTTP/2 404</d:status>"
        "</d:propstat>"
        "<d:propstat>"
        "<d:prop>"
        "<d:resourcetype><d:collection/><card:addressbook/></d:resourcetype>"
        "<d:displayname>Contacts</d:displayname>"
        "</d:prop>"
        "<d:status>HTTP/2 200</d:status>"
        "</d:propstat>"
        "</d:response>"
        "</d:multistatus>"
    )
    books = parse_addressbooks(body, base_url)
    assert [b.name for b in books] == ["Contacts"]


def test_parse_addressbooks_drops_cross_origin_href(base_url):
    body = (
        '<d:multistatus xmlns:d="DAV:" '
        'xmlns:card="urn:ietf:params:xml:ns:carddav">'
        "<d:response>"
        "<d:href>https://evil.example/dav/book/</d:href>"
        "<d:propstat>"
        "<d:prop>"
        "<d:resourcetype><d:collection/><card:addressbook/></d:resourcetype>"
        "<d:displayname>Evil</d:displayname>"
        "</d:prop>"
        "<d:status>HTTP/1.1 200 OK</d:status>"
        "</d:propstat>"
        "</d:response>"
        "</d:multistatus>"
    )
    assert parse_addressbooks(body, base_url) == []


def test_resolve_href_same_origin_rejects_cross_origin():
    with pytest.raises(CardDavError):
        resolve_href_same_origin(
            "https://good.example/dav/", "http://169.254.169.254/latest/"
        )


def test_resolve_href_same_origin_allows_same_host():
    out = resolve_href_same_origin(
        "https://good.example/dav/", "/dav/principals/alice/"
    )
    assert out == "https://good.example/dav/principals/alice/"


def test_discover_falls_back_to_base_url(base_url):
    """A server that returns no current-user-principal must still list books by
    PROPFINDing base_url directly (the Radicale account-URL case)."""

    class RadicaleSession:
        def request(self, method, url, *, body=None, headers=None):
            if method == "PROPFIND" and "current-user-principal" in (body or ""):
                # No principal advertised at this collection URL.
                return DavResponse(
                    207, '<d:multistatus xmlns:d="DAV:"></d:multistatus>')
            # Any other PROPFIND (the fallback Depth:1 on base_url) lists books.
            return DavResponse(207, load_fixture("addressbooks.xml"))

    books = list_addressbooks(RadicaleSession(), base_url)
    assert [b.name for b in books] == ["Contacts", "Work"]
