import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from caelum.config import Config, validate
from caelum.providers import Providers


@pytest.mark.parametrize("status,reply_text,raw,expected,mode", [
    (200, "Hello there.", "hello there", "Hello there.", "local_model"),
    (200, "Shopping list: tea and milk", "Shopping list first tea second milk",
     "Shopping list:\n\n1. Tea\n2. Milk", "local_rules"),
    (200, "Shopping list:\n\n1. Tea\n2. Milk\n3. Coffee", "Shopping list first tea second milk",
     "Shopping list:\n\n1. Tea\n2. Milk", "local_rules"),
    (307, "", "Shopping list first tea second milk", "Shopping list:\n\n1. Tea\n2. Milk", "local_rules"),
    (503, "", "Shopping list first tea second milk", "Shopping list:\n\n1. Tea\n2. Milk", "local_rules"),
])
async def test_opt_in_local_refiner_uses_loopback_and_never_cloud(monkeypatch, status, reply_text, raw, expected, mode):
    requests = []

    async def reply(reader, writer):
        headers = (await reader.readuntil(b"\r\n\r\n")).decode().lower()
        length = int(headers.split("content-length: ")[1].split("\r\n")[0])
        requests.append((headers, json.loads(await reader.readexactly(length))))
        body = json.dumps({"choices": [{"message": {"content": reply_text}}]}).encode()
        redirect = b"Location: /must-not-follow\r\n" if status == 307 else b""
        writer.write(f"HTTP/1.1 {status} Reply\r\n".encode() + redirect
                     + b"Content-Type: application/json\r\nContent-Length: "
                     + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    async with await asyncio.start_server(reply, "127.0.0.1", 0) as server:
        config = Config()
        config.stt.engine = "local"
        config.cleanup.model = "cloud-model"
        config.cleanup.local_model = "local-editor"
        port = server.sockets[0].getsockname()[1]
        config.cleanup.local_base_url = f"http://127.0.0.1:{port}/v1"
        cloud = AsyncMock()
        provider = Providers(config, client=cloud, credential_resolver=lambda _: pytest.fail("key"))
        try:
            assert await provider.cleanup(raw) == (expected, True)
            assert provider.metrics["cleanup_mode"] == mode
            if mode == "local_rules":
                assert provider.metrics["cleanup_error"] == "local_refinement_fallback"
            assert len(requests) == 1
            headers, body = requests[0]
            assert headers.startswith("post /v1/chat/completions ")
            assert "authorization:" not in headers
            assert body["model"] == "local-editor"
            assert body["messages"][-1]["content"] == (raw if mode == "local_model" else expected)
            cloud.post.assert_not_called()
        finally:
            await provider.aclose()


@pytest.mark.parametrize("url", ["https://api.example.org/v1", "http://localhost.evil/v1",
                                 "http://127.0.0.1@remote.test/v1", "http://127.0.0.1:bad/v1"])
def test_local_refiner_rejects_nonlocal_or_invalid_endpoints(url):
    config = Config()
    config.cleanup.local_base_url = url
    with pytest.raises(ValueError):
        validate(config)
