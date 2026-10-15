import pytest

from attachments.client_ip import client_ip


def test_client_ip_uses_remote_addr_when_no_trusted_proxy():
    meta = {"REMOTE_ADDR": "203.0.113.7", "HTTP_X_FORWARDED_FOR": "9.9.9.9"}

    assert client_ip(meta, trusted_hops=0) == "203.0.113.7"


def test_client_ip_counts_trusted_hops_from_right():
    meta = {
        "REMOTE_ADDR": "10.0.0.5",
        "HTTP_X_FORWARDED_FOR": "9.9.9.9, 203.0.113.7, 70.1.1.1",
    }

    assert client_ip(meta, trusted_hops=2) == "203.0.113.7"


def test_client_ip_ignores_spoofed_leftmost_xff():
    meta = {
        "REMOTE_ADDR": "10.0.0.5",
        "HTTP_X_FORWARDED_FOR": "6.6.6.6, 9.9.9.9, 203.0.113.7, 70.1.1.1",
    }

    assert client_ip(meta, trusted_hops=2) == "203.0.113.7"


@pytest.mark.parametrize(
    "meta",
    [
        {"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "70.1.1.1"},
        {"REMOTE_ADDR": "10.0.0.5"},
    ],
)
def test_client_ip_with_fewer_xff_entries_than_hops_falls_back_safely(meta):
    assert client_ip(meta, trusted_hops=2) is None


@pytest.mark.parametrize(
    ("meta", "hops"),
    [
        ({"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "9.9.9.9, garbage"}, 1),
        ({"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "203.0.113.7:80"}, 1),
        ({"REMOTE_ADDR": "10.0.0.5"}, 1),
        ({"REMOTE_ADDR": "not-an-ip"}, 0),
    ],
)
def test_client_ip_invalid_value_becomes_null(meta, hops):
    assert client_ip(meta, trusted_hops=hops) is None


def test_client_ip_strips_whitespace_around_entries():
    meta = {"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "9.9.9.9,203.0.113.7 ,  70.1.1.1"}

    assert client_ip(meta, trusted_hops=2) == "203.0.113.7"


@pytest.mark.parametrize(
    ("meta", "hops"),
    [
        ({"REMOTE_ADDR": "2001:db8:0:0::1"}, 0),
        ({"REMOTE_ADDR": "10.0.0.5", "HTTP_X_FORWARDED_FOR": "2001:DB8:0:0::1, 70.1.1.1"}, 2),
    ],
)
def test_client_ip_supports_ipv6(meta, hops):
    assert client_ip(meta, trusted_hops=hops) == "2001:db8::1"
