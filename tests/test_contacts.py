import vobject

from carddav_client.contacts import (
    Contact,
    build_vcard,
    format_contact_full,
    format_contact_line,
    format_contact_list,
    matches,
    parse_cards,
    parse_vcard,
)
from carddav_client.dav import parse_address_data
from tests.conftest import load_fixture

JOHN = """BEGIN:VCARD
VERSION:3.0
UID:john-doe-uid
FN:John Doe
N:Doe;John;;;
EMAIL;TYPE=WORK:john@acme.example
EMAIL;TYPE=HOME:john@home.example
TEL;TYPE=CELL:+1-202-555-0143
ORG:Acme;Engineering
TITLE:Senior Engineer
END:VCARD
"""


def test_parse_vcard_all_fields():
    c = parse_vcard(JOHN, href="/x/john.vcf")
    assert c.full_name == "John Doe"
    assert c.uid == "john-doe-uid"
    assert c.emails == ["john@acme.example", "john@home.example"]
    assert c.phones == ["+1-202-555-0143"]
    assert c.org == "Acme; Engineering"
    assert c.title == "Senior Engineer"
    assert c.href == "/x/john.vcf"


def test_parse_cards_skips_malformed(base_url):
    raws = parse_address_data(load_fixture("query.xml"), base_url)
    contacts = parse_cards(raws)
    # 2 valid cards; the "this is not a vcard" entry is dropped
    names = sorted(c.full_name for c in contacts)
    assert names == ["John Doe", "Mary Jane"]


def test_build_vcard_roundtrips():
    uid, text = build_vcard(
        "Jane Roe",
        emails=["jane@x.example", " "],
        phones=["+44 20 7946 0991"],
        org="MyCo",
        title="CTO",
    )
    assert uid
    card = vobject.readOne(text)
    assert card.fn.value == "Jane Roe"
    assert card.uid.value == uid
    assert [e.value for e in card.contents["email"]] == ["jane@x.example"]
    assert card.org.value == ["MyCo"]
    # round-trip back through our parser
    c = parse_vcard(text)
    assert c.full_name == "Jane Roe"
    assert c.emails == ["jane@x.example"]
    assert c.phones == ["+44 20 7946 0991"]
    assert c.org == "MyCo"
    assert c.title == "CTO"


def test_build_vcard_requires_name():
    try:
        build_vcard("   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty name")


def test_matches():
    c = parse_vcard(JOHN)
    assert matches(c, "john")
    assert matches(c, "ACME")
    assert matches(c, "home.example")
    assert not matches(c, "zzz")
    assert matches(c, "")  # empty query matches everything


def test_matches_phone():
    c = parse_vcard(JOHN)
    assert matches(c, "+1-202-555-0143")  # exact formatted number
    assert matches(c, "555")  # substring of the raw value
    assert matches(c, "5550143")  # digit-only match across separators
    assert not matches(c, "999")


def test_format_contact_line():
    c = parse_vcard(JOHN)
    line = format_contact_line(c)
    assert line.startswith("- John Doe — ")
    assert "Acme; Engineering" in line
    assert "john@acme.example" in line
    assert "{" not in line


def test_format_contact_full():
    text = format_contact_full(parse_vcard(JOHN))
    assert text.startswith("John Doe")
    assert "Emails: john@acme.example, john@home.example" in text
    assert "Phones: +1-202-555-0143" in text
    assert "UID: john-doe-uid" in text


def test_format_contact_list_empty():
    assert format_contact_list([], "Contacts") == "Contacts: none found."


def test_format_contact_list_count():
    contacts = [Contact(full_name=f"P{i}") for i in range(3)]
    out = format_contact_list(contacts, "Contacts")
    assert out.startswith("Contacts: 3 contact(s)")
    assert out.count("\n- ") == 3  # one line per contact
