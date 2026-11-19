"""Dispatching of realtime pushes."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from custom_components.gruenbeck.api.realtime import GruenbeckRealtime

from .conftest import REALTIME, SERIAL


async def test_dispatch_and_refresh() -> None:
    """Frames reach the callback of the matching serial only."""
    client = MagicMock()
    client.async_realtime = AsyncMock(return_value={"mflow1": 1.2})
    realtime = GruenbeckRealtime(client, MagicMock(), {SERIAL: "softliQ.D/X"})
    received: list[dict] = []
    remove = realtime.register(SERIAL, received.append)
    frame = json.dumps(
        {"type": 1, "target": "SendMessageToDevice", "arguments": [REALTIME, {"id": "OTHER"}]}
    )
    realtime._handle_frame(frame + "\x1e")
    assert received == [REALTIME]
    assert realtime.last_message is not None
    await realtime.async_refresh()
    assert received[-1] == {"mflow1": 1.2}
    assert [c.args[1] for c in client.async_realtime.await_args_list] == ["enter", "refresh"]
    remove()
    realtime._handle_frame(frame)
    assert len(received) == 2
