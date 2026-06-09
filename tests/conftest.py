from pathlib import Path

import pytest

from carddav_client.http import DavResponse

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeDavSession:
    """A scripted DavSession: routes PROPFIND/REPORT by request body, records PUTs.

    Mirrors the discovery flow (current-user-principal -> addressbook-home-set ->
    PROPFIND address books -> REPORT addressbook-query) without any real network.
    """

    def __init__(self) -> None:
        self.put_calls: list[tuple[str, str, dict]] = []
        self.put_status = 201

    def request(self, method, url, *, body=None, headers=None):
        headers = headers or {}
        if method == "PROPFIND":
            if "current-user-principal" in (body or ""):
                return DavResponse(207, load_fixture("principal.xml"))
            if "addressbook-home-set" in (body or ""):
                return DavResponse(207, load_fixture("home.xml"))
            return DavResponse(207, load_fixture("addressbooks.xml"))
        if method == "REPORT":
            return DavResponse(207, load_fixture("query.xml"))
        if method == "PUT":
            self.put_calls.append((url, body or "", headers))
            return DavResponse(self.put_status, "")
        raise AssertionError(f"unexpected method {method} {url}")


@pytest.fixture
def session():
    return FakeDavSession()


@pytest.fixture
def base_url():
    return "https://example.com/remote.php/dav/"
