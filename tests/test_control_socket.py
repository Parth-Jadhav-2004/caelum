import asyncio
import os
import socket
import struct
from unittest.mock import AsyncMock, Mock

import pytest
from caelum.service import handle_control_request

pytestmark = pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="Linux control socket")


@pytest.fixture
def writer():
    writer = Mock(spec=asyncio.StreamWriter)
    writer.get_extra_info.return_value.getsockopt.return_value = struct.pack("3i", 0, os.getuid(), 0)
    return writer


@pytest.mark.parametrize(
    "frame",
    [b"oops\n", b"\xff\n", b"null\n", b"", b'{"action":"status"}', b" " * 31 + b"{}\n", None],
    ids=["json", "encoding", "non-object", "empty", "missing-newline", "over-limit", "timeout"],
)
async def test_invalid_request_is_answered_without_dispatch(frame, writer):
    reader = asyncio.StreamReader(limit=32)
    if frame is not None:
        reader.feed_data(frame)
        reader.feed_eof()
    dispatch = AsyncMock()
    await asyncio.wait_for(handle_control_request(reader, writer, dispatch=dispatch), 3)
    dispatch.assert_not_awaited()
    writer.write.assert_called_once_with(b'{"error": "Invalid request"}\n')
    writer.drain.assert_awaited_once()
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


async def test_valid_request_returns_dispatch_reply(writer):
    reader = asyncio.StreamReader()
    reader.feed_data(b'{"action":"status"}\n')
    dispatch = AsyncMock(return_value={"ok": True})
    await asyncio.wait_for(handle_control_request(reader, writer, dispatch=dispatch), 3)
    dispatch.assert_awaited_once_with({"action": "status"})
    writer.write.assert_called_once_with(b'{"ok": true}\n')
    writer.close.assert_called_once()


async def test_other_uid_is_closed_before_read(writer):
    writer.get_extra_info.return_value.getsockopt.return_value = struct.pack("3i", 0, os.getuid() + 1, 0)
    reader = AsyncMock(spec=asyncio.StreamReader)
    dispatch = AsyncMock()
    await handle_control_request(reader, writer, dispatch=dispatch)
    reader.readuntil.assert_not_awaited()
    dispatch.assert_not_awaited()
    writer.write.assert_not_called()
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()


async def test_disconnected_peer_is_closed(writer):
    reader = asyncio.StreamReader()
    reader.feed_eof()
    writer.drain.side_effect = BrokenPipeError
    writer.wait_closed.side_effect = BrokenPipeError
    await asyncio.wait_for(handle_control_request(reader, writer, dispatch=AsyncMock()), 3)
    writer.close.assert_called_once()
    writer.wait_closed.assert_awaited_once()
