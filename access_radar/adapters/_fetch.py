"""Minimal stdlib JSON fetcher used only when no fetch callable is injected.

Adapters take `fetch(url, headers=None) -> parsed JSON` so access_run can pass the shared
rate-limited / circuit-breaking client instead. Tests always inject a fake and never touch the network.
"""
import json
import urllib.request

UA = "access-radar/0.1"


class FetchError(Exception):
    pass


def default_fetch(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - surface any network / parse failure uniformly
        raise FetchError(f"{type(e).__name__}: {e}") from e
