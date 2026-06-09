from carddav_client.api import (
    create_contact,
    get_addressbooks,
    get_contact,
    get_contacts,
    search_contacts,
)


def test_get_addressbooks(session, base_url):
    books = get_addressbooks(session, base_url)
    assert [b.name for b in books] == ["Contacts", "Work"]


def test_get_contacts_default_book(session, base_url):
    book, contacts = get_contacts(session, base_url)
    assert book.name == "Contacts"
    assert sorted(c.full_name for c in contacts) == ["John Doe", "Mary Jane"]


def test_search_contacts(session, base_url):
    book, found = search_contacts(session, base_url, "mary")
    assert [c.full_name for c in found] == ["Mary Jane"]
    _, none = search_contacts(session, base_url, "zzz")
    assert none == []


def test_get_contact_by_name(session, base_url):
    _, contact, _ = get_contact(session, base_url, "John Doe")
    assert contact is not None
    assert contact.uid == "john-doe-uid"


def test_get_contact_by_uid(session, base_url):
    _, contact, _ = get_contact(session, base_url, "mary-jane-uid")
    assert contact is not None
    assert contact.full_name == "Mary Jane"


def test_get_contact_no_match(session, base_url):
    _, contact, candidates = get_contact(session, base_url, "nobody")
    assert contact is None
    assert candidates == []


def test_get_contact_returns_candidates_without_extra_report(session, base_url):
    # An ambiguous identifier should surface the candidate list directly from
    # get_contact, so the tool need not issue a second REPORT to enumerate them.
    _, contact, candidates = get_contact(session, base_url, "example")
    assert contact is None
    assert sorted(c.full_name for c in candidates) == ["John Doe", "Mary Jane"]


def test_create_contact_puts_vcard(session, base_url):
    book, contact = create_contact(
        session, base_url,
        full_name="Carol King",
        emails=["carol@example.net"],
        phones=["+1-555-0100"],
        org="Initech",
        addressbook="work",
    )
    assert book.name == "Work"
    assert contact.full_name == "Carol King"
    assert contact.href.endswith(f"/{contact.uid}.vcf")

    assert len(session.put_calls) == 1
    url, body, headers = session.put_calls[0]
    assert url.startswith(
        "https://example.com/remote.php/dav/addressbooks/users/alice/work/")
    assert "FN:Carol King" in body
    assert "carol@example.net" in body
    assert headers.get("If-None-Match") == "*"
    assert headers.get("Content-Type", "").startswith("text/vcard")
