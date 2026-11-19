"""Realtime channel over the Azure SignalR hub ``gruenbeck``.

One connection serves all devices of an account; messages carry the serial
number in ``id`` and are dispatched to the matching callback. The channel
reconnects on its own with exponential backoff and never raises into Home
Assistant. Protocol details follow ``pygruenbeck_cloud`` and
``ioBroker.gruenbeck`` (both MIT).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from datetime import UTC, datetime
import json
import logging
from typing import Any, Final

import aiohttp
from yarl import URL

from .client import USER_AGENT, GruenbeckClient
from .exceptions import GruenbeckAuthError, GruenbeckError

_LOGGER = logging.getLogger(__name__)

WS_HOST: Final = "prod-eu-gruenbeck-signalr.service.signalr.net"
RECORD_SEPARATOR: Final = "\x1e"
HANDSHAKE: Final = '{"protocol":"json","version":1}' + RECORD_SEPARATOR
MESSAGE_INVOCATION: Final = 1
MESSAGE_PING: Final = 6
MESSAGE_CLOSE: Final = 7
DATA_TARGETS: Final = ("SendMessageToDevice", "SendOneTimeMessageToDevice")
BACKOFF_START: Final = 30.0
BACKOFF_MAX: Final = 900.0
REFRESH_INTERVAL: Final = 360.0

RealtimeCallback = Callable[[dict[str, Any]], None]
StateCallback = Callable[[bool], None]


def split_messages(frame: str) -> list[dict[str, Any]]:
    """Split a SignalR text frame into JSON records, skipping garbage."""
    result: list[dict[str, Any]] = []
    for chunk in frame.split(RECORD_SEPARATOR):
        part = chunk.strip()
        if not part:
            continue
        try:
            record = json.loads(part)
        except ValueError:
            _LOGGER.debug("Skipping non-JSON realtime record: %.200s", part)
            continue
        if isinstance(record, dict):
            result.append(record)
    return result


def device_updates(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the per-device payloads contained in an invocation record."""
    if record.get("type") != MESSAGE_INVOCATION:
        return []
    if record.get("target") not in DATA_TARGETS:
        return []
    arguments = record.get("arguments")
    if not isinstance(arguments, list):
        return []
    return [arg for arg in arguments if isinstance(arg, dict) and arg.get("id")]


class GruenbeckRealtime:
    """Keeps the SignalR connection of one account alive."""

    def __init__(
        self,
        client: GruenbeckClient,
        session: aiohttp.ClientSession,
        device_ids: dict[str, str],
    ) -> None:
        """``device_ids`` maps serial number to cloud device id."""
        self._client = client
        self._session = session
        self._device_ids = device_ids
        self._listeners: dict[str, RealtimeCallback] = {}
        self._state_listeners: list[StateCallback] = []
        self._task: asyncio.Task[None] | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self.connected = False
        self.last_message: datetime | None = None
        self.last_error: str | None = None
        self.reconnects = 0

    def register(self, serial: str, callback: RealtimeCallback) -> Callable[[], None]:
        """Register a callback for one device."""
        self._listeners[serial] = callback

        def _remove() -> None:
            self._listeners.pop(serial, None)

        return _remove

    def register_state(self, callback: StateCallback) -> Callable[[], None]:
        """Register a callback for connect/disconnect changes."""
        self._state_listeners.append(callback)
        return lambda: self._state_listeners.remove(callback)

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            for callback in list(self._state_listeners):
                callback(value)

    def start(self, create_task: Callable[..., asyncio.Task[None]]) -> None:
        """Start the background loop using Home Assistant's task factory."""
        if self._task is None or self._task.done():
            self._task = create_task(self._run(), "gruenbeck_realtime")

    async def stop(self) -> None:
        """Leave realtime mode and close the connection."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self._close()

    async def _close(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None
        self._set_connected(False)

    async def async_refresh(self) -> None:
        """Ask every device to (re)send realtime values."""
        for serial, device_id in self._device_ids.items():
            try:
                await self._client.async_realtime(device_id, "enter")
                values = await self._client.async_realtime(device_id, "refresh")
            except GruenbeckError as err:
                _LOGGER.debug("Realtime refresh for %s failed: %s", serial, err)
                continue
            if values and serial in self._listeners:
                self._listeners[serial](values)

    async def _run(self) -> None:
        backoff = BACKOFF_START
        while True:
            try:
                await self._connect_and_listen()
                backoff = BACKOFF_START
            except asyncio.CancelledError:
                raise
            except GruenbeckAuthError as err:
                self.last_error = f"auth: {err}"
                _LOGGER.warning("Realtime channel: authentication failed: %s", err)
            except (GruenbeckError, aiohttp.ClientError, TimeoutError) as err:
                self.last_error = str(err)
                _LOGGER.debug("Realtime channel dropped: %s", err)
            except Exception as err:
                self.last_error = repr(err)
                _LOGGER.exception("Unexpected error in realtime channel")
            await self._close()
            self.reconnects += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX)

    async def _connect_and_listen(self) -> None:
        negotiation = await self._client.async_negotiate()
        hub_token = negotiation["accessToken"]
        negotiate_url = URL.build(
            scheme="https", host=WS_HOST, path="/client/negotiate", query={"hub": "gruenbeck"}
        )
        async with self._session.post(
            negotiate_url,
            headers={
                "Authorization": f"Bearer {hub_token}",
                "User-Agent": USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != 200:
                raise GruenbeckError(f"SignalR negotiate answered {resp.status}")
            connection = await resp.json(content_type=None)
        connection_id = connection.get("connectionToken") or connection.get("connectionId")
        if not connection_id:
            raise GruenbeckError("SignalR negotiate without connection id")
        ws_url = URL.build(
            scheme="wss",
            host=WS_HOST,
            path="/client/",
            query={"hub": "gruenbeck", "id": connection_id, "access_token": hub_token},
        )
        self._ws = await self._session.ws_connect(
            ws_url, heartbeat=30, headers={"User-Agent": USER_AGENT}
        )
        await self._ws.send_str(HANDSHAKE)
        self._set_connected(True)
        self.last_error = None
        await self.async_refresh()
        refresher = asyncio.get_running_loop().create_task(self._refresh_loop())
        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._handle_frame(msg.data)
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
        finally:
            refresher.cancel()
        raise GruenbeckError("SignalR connection closed")

    async def _refresh_loop(self) -> None:
        """Keep realtime mode active; the cloud stops pushing otherwise."""
        while True:
            await asyncio.sleep(REFRESH_INTERVAL)
            await self.async_refresh()

    def _handle_frame(self, frame: str) -> None:
        for record in split_messages(frame):
            if record.get("type") == MESSAGE_CLOSE:
                _LOGGER.debug("SignalR close message: %s", record.get("error"))
                continue
            for update in device_updates(record):
                serial = str(update.get("id"))
                callback = self._listeners.get(serial)
                if callback is None:
                    _LOGGER.debug("Realtime values for unknown device %s", serial)
                    continue
                self.last_message = datetime.now(UTC)
                callback(update)
