"""HTTP client for the Grünbeck cloud.

The login reproduces the Azure AD B2C flow of the Grünbeck app (authorization
code with PKCE). Endpoints, client id and the login sequence were taken from
``pygruenbeck_cloud`` (MIT, Copyright (c) 2024 Marco Neumann) and
``ioBroker.gruenbeck`` (MIT, Copyright (c) 2021-2030 tombox).
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import re
import secrets
from typing import Any, Final
from urllib.parse import unquote

import aiohttp
from yarl import URL

from .exceptions import (
    GruenbeckAuthError,
    GruenbeckConnectionError,
    GruenbeckParameterError,
    GruenbeckRateLimitError,
    GruenbeckResponseError,
    GruenbeckServerError,
)
from .models import GruenbeckDevice

_LOGGER = logging.getLogger(__name__)

LOGIN_HOST: Final = "gruenbeckb2c.b2clogin.com"
LOGIN_TENANT_PATH: Final = "/a50d35c1-202f-4da7-aa87-76e51a3098c6/b2c_1a_signinup"
CLIENT_ID: Final = "5a83cc16-ffb1-42e9-9859-9fbf07f36df8"
REDIRECT_URI: Final = f"msal{CLIENT_ID}://auth"
SCOPE: Final = (
    "https://gruenbeckb2c.onmicrosoft.com/iot/user_impersonation openid profile offline_access"
)
API_HOST: Final = "prod-eu-gruenbeck-api.azurewebsites.net"
API_VERSION: Final = "2024-05-02"
USER_AGENT: Final = "Gruenbeck/354 CFNetwork/1209 Darwin/20.2.0"
REQUEST_TIMEOUT: Final = aiohttp.ClientTimeout(total=30)
TOKEN_REFRESH_MARGIN: Final = timedelta(minutes=10)

_SETTINGS_RE: Final = re.compile(r"^var SETTINGS = (.+);", re.MULTILINE)
_CODE_RE: Final = re.compile(r"code%3d([^%&\"'>]+)", re.IGNORECASE)

_MSAL_HEADERS: Final = {
    "x-client-SKU": "MSAL.iOS",
    "x-client-OS": "14.3",
    "x-client-CPU": "64",
    "x-client-DM": "iPhone",
    "x-client-Ver": "0.8.0",
    "x-app-name": "Grünbeck",
    "x-app-ver": "1.2.0",
    "Accept-Language": "de-de",
    "User-Agent": USER_AGENT,
}


@dataclass
class AuthToken:
    """Access and refresh token of the cloud session."""

    access_token: str
    refresh_token: str
    expires_on: datetime
    tenant: str

    @property
    def expired(self) -> bool:
        """Return True if the token must be renewed now."""
        return datetime.now(UTC) >= self.expires_on - TOKEN_REFRESH_MARGIN


def _pkce_pair() -> tuple[str, str]:
    """Return verifier and S256 challenge in base64url without padding."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def _token_from_response(payload: dict[str, Any], tenant: str) -> AuthToken:
    try:
        access = payload["access_token"]
        refresh = payload["refresh_token"]
    except KeyError as err:
        raise GruenbeckAuthError(f"Token response without {err}") from err
    expires_on: datetime
    if "expires_on" in payload:
        expires_on = datetime.fromtimestamp(int(payload["expires_on"]), UTC)
    else:
        expires_on = datetime.now(UTC) + timedelta(seconds=int(payload.get("expires_in", 3600)))
    return AuthToken(access, refresh, expires_on, tenant)


class GruenbeckClient:
    """Async client for one Grünbeck cloud account."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Initialise with a dedicated aiohttp session (needs its own cookies)."""
        self._session = session
        self._username = username
        self._password = password
        self._token: AuthToken | None = None
        self._login_lock = asyncio.Lock()
        self._sleep = sleep
        self.last_request: datetime | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """The dedicated HTTP session of this account."""
        return self._session

    @property
    def username(self) -> str:
        """Account name."""
        return self._username

    # ------------------------------------------------------------------ auth

    async def async_login(self) -> None:
        """Run the full B2C login and store the token."""
        verifier, challenge = _pkce_pair()
        self._session.cookie_jar.clear()
        query = {
            "x-client-Ver": "0.8.0",
            "state": base64.urlsafe_b64encode(secrets.token_bytes(24)).decode(),
            "client_info": "1",
            "response_type": "code",
            "code_challenge_method": "S256",
            "x-app-name": "Grünbeck",
            "x-client-OS": "14.3",
            "x-app-ver": "1.2.1",
            "scope": SCOPE,
            "x-client-SKU": "MSAL.iOS",
            "code_challenge": challenge,
            "x-client-CPU": "64",
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "haschrome": "1",
            "return-client-request-id": "true",
            "x-client-DM": "iPhone",
        }
        url = URL.build(
            scheme="https",
            host=LOGIN_HOST,
            path=f"{LOGIN_TENANT_PATH}/oauth2/v2.0/authorize",
            query=query,
        )
        page = await self._raw_request(
            "GET",
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "de-de",
                "User-Agent": USER_AGENT,
            },
        )
        match = _SETTINGS_RE.search(page)
        if not match:
            raise GruenbeckResponseError("Login page without SETTINGS block")
        settings_json = re.sub(
            r'"sanitizerPolicy":(.+?),"hosts"',
            r'"sanitizerPolicy":"x","hosts"',
            match[1],
        )
        try:
            settings = json.loads(settings_json)
            csrf = settings["csrf"]
            trans_id = settings["transId"]
            policy = settings["hosts"]["policy"]
            tenant = settings["hosts"]["tenant"]
        except (ValueError, KeyError, TypeError) as err:
            raise GruenbeckResponseError("Unreadable login SETTINGS block") from err

        url = URL.build(
            scheme="https",
            host=LOGIN_HOST,
            path=f"{tenant}/SelfAsserted",
            query={"tx": trans_id, "p": policy},
        )
        answer = await self._raw_request(
            "POST",
            url,
            headers={
                "X-CSRF-TOKEN": csrf,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": f"https://{LOGIN_HOST}",
                "User-Agent": USER_AGENT,
            },
            data={
                "request_type": "RESPONSE",
                "signInName": self._username,
                "password": self._password,
            },
        )
        try:
            status = json.loads(answer).get("status")
        except ValueError:
            status = None
        if str(status) != "200":
            raise GruenbeckAuthError("Grünbeck cloud rejected the credentials")

        url = URL.build(
            scheme="https",
            host=LOGIN_HOST,
            path=f"{tenant}/api/CombinedSigninAndSignup/confirmed",
            query={"csrf_token": csrf, "tx": trans_id, "p": policy},
        )
        redirect = await self._raw_request(
            "GET", url, headers={"User-Agent": USER_AGENT}, expected=(302,)
        )
        code_match = _CODE_RE.search(redirect)
        if not code_match:
            raise GruenbeckAuthError("Login did not return an authorization code")
        code = unquote(code_match[1])

        url = URL.build(scheme="https", host=LOGIN_HOST, path=f"{tenant}/oauth2/v2.0/token")
        payload = await self._raw_request(
            "POST",
            url,
            headers={**_MSAL_HEADERS, "Accept": "application/json"},
            data={
                "client_info": "1",
                "scope": SCOPE,
                "code": code,
                "grant_type": "authorization_code",
                "code_verifier": verifier,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
            },
            as_json=True,
        )
        self._token = _token_from_response(payload, tenant)
        _LOGGER.debug("Logged in, token valid until %s", self._token.expires_on)

    async def _async_refresh(self) -> None:
        assert self._token is not None
        url = URL.build(
            scheme="https",
            host=LOGIN_HOST,
            path=f"{self._token.tenant}/oauth2/v2.0/token",
        )
        try:
            payload = await self._raw_request(
                "POST",
                url,
                headers={**_MSAL_HEADERS, "Accept": "application/json"},
                data={
                    "client_info": "1",
                    "scope": SCOPE,
                    "grant_type": "refresh_token",
                    "refresh_token": self._token.refresh_token,
                    "client_id": CLIENT_ID,
                },
                as_json=True,
            )
            self._token = _token_from_response(payload, self._token.tenant)
        except (GruenbeckAuthError, GruenbeckResponseError, GruenbeckServerError):
            _LOGGER.debug("Token refresh failed, logging in again")
            self._token = None
            await self.async_login()

    async def async_access_token(self) -> str:
        """Return a valid access token, renewing it if necessary."""
        async with self._login_lock:
            if self._token is None:
                await self.async_login()
            elif self._token.expired:
                await self._async_refresh()
            assert self._token is not None
            return self._token.access_token

    def invalidate_token(self) -> None:
        """Force a refresh before the next request (after HTTP 401)."""
        if self._token is not None:
            self._token.expires_on = datetime.now(UTC)

    # --------------------------------------------------------------- transport

    async def _raw_request(
        self,
        method: str,
        url: URL,
        *,
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        json_body: Any = None,
        expected: tuple[int, ...] = (200,),
        as_json: bool = False,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                data=data,
                json=json_body,
                allow_redirects=False,
                timeout=REQUEST_TIMEOUT,
            ) as resp:
                text = await resp.text()
                self.last_request = datetime.now(UTC)
                if resp.status == 429:
                    retry = resp.headers.get("Retry-After")
                    raise GruenbeckRateLimitError(
                        f"Rate limited by {url.host}",
                        float(retry) if retry and retry.isdigit() else None,
                    )
                if resp.status in (401, 403):
                    raise GruenbeckAuthError(f"{url.path} answered {resp.status}")
                if resp.status >= 500 and resp.status not in expected:
                    raise GruenbeckServerError(f"{url.path} answered {resp.status}", resp.status)
                if resp.status not in expected:
                    raise GruenbeckResponseError(
                        f"{url.path} answered {resp.status}, expected {expected}"
                    )
                if as_json:
                    try:
                        return json.loads(text) if text else None
                    except ValueError as err:
                        raise GruenbeckResponseError(f"{url.path} returned no JSON") from err
                return text
        except (aiohttp.ClientError, TimeoutError) as err:
            raise GruenbeckConnectionError(f"{url.host}: {err}") from err

    async def _api(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        """Authenticated API call with one transparent re-login on 401."""
        url = URL.build(
            scheme="https", host=API_HOST, path=path, query={"api-version": API_VERSION}
        )
        for attempt in (1, 2):
            token = await self.async_access_token()
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "de-de",
                "User-Agent": USER_AGENT,
                "Authorization": f"Bearer {token}",
                "cache-control": "no-cache",
            }
            try:
                return await self._raw_request(
                    method,
                    url,
                    headers=headers,
                    json_body=json_body,
                    expected=expected,
                    as_json=True,
                )
            except GruenbeckAuthError:
                if attempt == 2:
                    raise
                self.invalidate_token()
        raise GruenbeckAuthError("unreachable")  # pragma: no cover

    # -------------------------------------------------------------------- API

    async def async_get_devices(self) -> list[GruenbeckDevice]:
        """Return all softliQ devices of the account."""
        payload = await self._api("GET", "/api/devices")
        if not isinstance(payload, list):
            raise GruenbeckResponseError("Device list is not a list")
        devices = [
            GruenbeckDevice.from_list_entry(entry)
            for entry in payload
            if isinstance(entry, dict) and entry.get("id")
        ]
        return [device for device in devices if device.is_softener]

    async def async_get_info(self, device_id: str) -> dict[str, Any]:
        """Return device information including errors and daily usage."""
        payload = await self._api("GET", f"/api/devices/{device_id}")
        if not isinstance(payload, dict):
            raise GruenbeckResponseError("Device info is not an object")
        return payload

    async def async_get_parameters(self, device_id: str) -> dict[str, Any]:
        """Return the parameter set of a device."""
        payload = await self._api("GET", f"/api/devices/{device_id}/parameters")
        if not isinstance(payload, dict):
            raise GruenbeckResponseError("Parameters are not an object")
        return payload

    async def async_get_measurements(self, device_id: str, kind: str) -> list[Any]:
        """Return daily ``water`` or ``salt`` measurements."""
        payload = await self._api("GET", f"/api/devices/{device_id}/measurements/{kind}")
        return payload if isinstance(payload, list) else []

    async def async_set_parameters(self, device_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """PATCH parameters; return the new parameter set."""
        payload = await self._api(
            "PATCH",
            f"/api/devices/{device_id}/parameters",
            json_body=changes,
            expected=(200, 500),
        )
        if isinstance(payload, dict) and "error" in payload:
            error = payload["error"]
            detail = error.get("type") if isinstance(error, dict) else error
            raise GruenbeckParameterError(f"Cloud rejected {list(changes)}: {detail}")
        if not isinstance(payload, dict):
            raise GruenbeckResponseError("Parameter update returned no object")
        return payload

    async def async_regenerate(self, device_id: str) -> None:
        """Start a manual regeneration."""
        await self._api(
            "POST", f"/api/devices/{device_id}/regenerate", json_body={}, expected=(200, 202)
        )

    async def async_realtime(self, device_id: str, action: str) -> dict[str, Any] | None:
        """POST realtime/enter, refresh or leave; refresh may return values."""
        payload = await self._api(
            "POST", f"/api/devices/{device_id}/realtime/{action}", expected=(200, 202)
        )
        return payload if isinstance(payload, dict) else None

    async def async_negotiate(self) -> dict[str, Any]:
        """Return SignalR url and access token."""
        payload = await self._api("GET", "/api/realtime/negotiate")
        if not isinstance(payload, dict) or "accessToken" not in payload:
            raise GruenbeckResponseError("Negotiation without accessToken")
        return payload
