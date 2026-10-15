import ipaddress
from collections.abc import Mapping


def client_ip(meta: Mapping[str, str], *, trusted_hops: int) -> str | None:
    if trusted_hops == 0:
        return _normalized(meta.get("REMOTE_ADDR", ""))
    entries = [e.strip() for e in meta.get("HTTP_X_FORWARDED_FOR", "").split(",")]
    if len(entries) < trusted_hops:
        return None
    return _normalized(entries[-trusted_hops])


def _normalized(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None
