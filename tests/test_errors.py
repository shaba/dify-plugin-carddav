from carddav_client.errors import redact_credentials
from tools._common import error_message


def test_redact_strips_userinfo_from_url():
    out = redact_credentials("failed at https://alice:s3cret@host.example/dav/")
    assert "s3cret" not in out
    assert "alice" not in out
    assert out == "failed at https://host.example/dav/"


def test_redact_leaves_clean_url_untouched():
    text = "failed at https://host.example/remote.php/dav/"
    assert redact_credentials(text) == text


def test_redact_handles_non_string():
    assert redact_credentials(ValueError("x://u:p@h")) == "x://h"


def test_password_in_base_url_absent_from_error_message():
    # An operator may embed credentials in base_url; the password must never
    # reach the LLM/end-user via the tool error text.
    base_url = "https://bob:hunter2@dav.example/remote.php/dav/"
    exc = Exception(f"connection refused to {base_url}")
    msg = error_message(exc)
    assert "hunter2" not in msg
    assert msg == ("CardDAV error: connection refused to "
                   "https://dav.example/remote.php/dav/")
