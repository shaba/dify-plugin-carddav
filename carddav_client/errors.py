import re


class CardDavError(Exception):
    pass


class DiscoveryError(CardDavError):
    pass


class ContactNotFound(CardDavError):
    pass


# Matches the userinfo portion of a URL (scheme://user:pass@host). Strip the
# password (and username) before any error string reaches the LLM/end-user, in
# case an operator configured base_url with embedded credentials.
_USERINFO_RE = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)[^/@\s]*@")


def redact_credentials(text: object) -> str:
    """Strip user:pass@ userinfo from any URL embedded in a message."""
    return _USERINFO_RE.sub(r"\g<scheme>", str(text))
