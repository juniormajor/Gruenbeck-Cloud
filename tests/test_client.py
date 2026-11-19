"""Login sequence and error mapping of the HTTP client."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.gruenbeck.api import (
    GruenbeckAuthError,
    GruenbeckClient,
    GruenbeckRateLimitError,
    GruenbeckServerError,
)

from .conftest import load_text


class _Resp:
    def __init__(self, status: int, text: str, headers: dict[str, str] | None = None):
        self.status = status
        self._text = text
        self.headers = headers or {}

    async def text(self) -> str:
        return self._text

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


class _Jar:
    def clear(self) -> None:
        pass


class FakeSession:
    """Maps (method, path suffix) to queued responses."""

    def __init__(self, routes: dict[tuple[str, str], list[_Resp]]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str]] = []
        self.cookie_jar = _Jar()

    def request(self, method: str, url: Any, **kwargs: Any) -> _Resp:
        path = str(url.path)
        self.calls.append((method, path))
        for (m, suffix), queue in self.routes.items():
            if m == method and path.endswith(suffix) and queue:
                return queue.pop(0) if len(queue) > 1 else queue[0]
        raise AssertionError(f"unexpected {method} {path}")


def _login_routes() -> dict[tuple[str, str], list[_Resp]]:
    return {
        ("GET", "/oauth2/v2.0/authorize"): [_Resp(200, load_text("login_step_1.txt"))],
        ("POST", "/SelfAsserted"): [_Resp(200, load_text("login_step_2.txt"))],
        ("GET", "/CombinedSigninAndSignup/confirmed"): [_Resp(302, load_text("login_step_3.txt"))],
        ("POST", "/oauth2/v2.0/token"): [_Resp(200, load_text("login_step_4.txt"))],
    }


async def test_login_and_devices() -> None:
    """The four login steps run and the device list is filtered."""
    routes = _login_routes()
    routes[("GET", "/api/devices")] = [_Resp(200, load_text("get_devices.txt"))]
    session = FakeSession(routes)
    client = GruenbeckClient(session, "user@example.com", "secret")  # type: ignore[arg-type]
    devices = await client.async_get_devices()
    assert [d.series for d in devices] == ["softliQ.D", "softliQ.SE"]
    assert [c[0] for c in session.calls] == ["GET", "POST", "GET", "POST", "GET"]


async def test_wrong_password() -> None:
    """A non-200 status from SelfAsserted is an auth error."""
    routes = _login_routes()
    routes[("POST", "/SelfAsserted")] = [_Resp(200, '{"status":"400"}')]
    client = GruenbeckClient(FakeSession(routes), "u", "p")  # type: ignore[arg-type]
    with pytest.raises(GruenbeckAuthError):
        await client.async_login()


@pytest.mark.parametrize(
    ("status", "exc"),
    [(500, GruenbeckServerError), (429, GruenbeckRateLimitError)],
)
async def test_server_errors(status: int, exc: type[Exception]) -> None:
    """5xx and 429 map to dedicated exceptions."""
    routes = _login_routes()
    routes[("GET", "/api/devices")] = [_Resp(status, "", {"Retry-After": "120"})]
    client = GruenbeckClient(FakeSession(routes), "u", "p")  # type: ignore[arg-type]
    with pytest.raises(exc):
        await client.async_get_devices()


async def test_401_relogin_once() -> None:
    """An expired token triggers one refresh and a retry."""
    routes = _login_routes()
    routes[("GET", "/api/devices")] = [
        _Resp(401, ""),
        _Resp(200, load_text("get_devices.txt")),
    ]
    session = FakeSession(routes)
    client = GruenbeckClient(session, "u", "p")  # type: ignore[arg-type]
    assert len(await client.async_get_devices()) == 2
