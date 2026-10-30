"""Opt-in checks on a real Omarchy login; no provider requests or transcript storage."""

import asyncio
import json
import os
import re
import sys
import time
from contextlib import suppress

import pytest

from caelum.config import App
from caelum.linux import Bindings, hypr_json, runtime_dir, target_at_press
from caelum.orchestrator import HUD

pytestmark = pytest.mark.skipif(
    os.environ.get("CAELUM_NATIVE_TESTS") != "1", reason="Requires an active Omarchy/Hyprland login"
)


def pills(data):
    return [
        (output, level, layer)
        for output, monitor in data.items()
        for level, layers in monitor["levels"].items()
        for layer in layers
        if layer["namespace"] == "caelum-recording-pill"
    ]


async def test_native_pill_protocol_geometry_focus_and_dismiss(monkeypatch, tmp_path):
    original = asyncio.create_subprocess_exec
    protocol_log = (tmp_path / "protocol.log").open("wb")

    async def spawn(*args, **kwargs):
        kwargs["env"]["WAYLAND_DEBUG"] = "client"
        kwargs["stderr"] = protocol_log
        return await original(*args, **kwargs)

    monkeypatch.setattr("caelum.orchestrator.asyncio.create_subprocess_exec", spawn)
    # The patched function also affects hyprctl, so only patch while starting the helper.
    hud = HUD(App())
    await hud.start()
    monkeypatch.setattr("caelum.orchestrator.asyncio.create_subprocess_exec", original)
    before = await hypr_json("activewindow")
    target = await target_at_press()
    try:
        start = time.monotonic()
        await hud.emit(
            {
                "session_id": "native-test",
                "sequence": 1,
                "state": "listening",
                "elapsed_ms": 0,
                "level": 0,
                "history": [0] * 17,
                "output": target.output,
                "error_code": "",
            }
        )
        found = []
        for _ in range(30):
            found = pills(await hypr_json("layers"))
            if found and (found[0][2]["w"], found[0][2]["h"]) == (280, 96):
                break
            await asyncio.sleep(0.01)
        visible_ms = (time.monotonic() - start) * 1000
        print(f"Warm IPC-to-mapped-surface observation: {visible_ms:.1f} ms")
        assert len(found) == 1
        output, level, layer = found[0]
        assert output == target.output and level == "3"
        assert (layer["w"], layer["h"]) == (280, 96)
        assert (await hypr_json("activewindow")).get("address") == before.get("address")
        for seq, state in enumerate(("recording", "processing", "refining", "success", "error"), 2):
            await hud.emit(
                {
                    "session_id": "native-test",
                    "sequence": seq,
                    "state": state,
                    "elapsed_ms": 100,
                    "level": 0,
                    "history": [0] * 17,
                    "output": target.output,
                    "error_code": "network",
                }
            )
            await asyncio.sleep(0.04)
            assert (await hypr_json("activewindow")).get("address") == before.get("address")
        await hud.emit({"session_id": "native-test", "sequence": 10, "state": "hidden"})
        await asyncio.sleep(0.22)
        assert not pills(await hypr_json("layers"))
    finally:
        await hud.close()
        protocol_log.close()
    protocol = (tmp_path / "protocol.log").read_text()
    assert "set_keyboard_interactivity(0)" in protocol
    assert "set_exclusive_zone(0)" in protocol
    regions = re.findall(r"set_input_region\(wl_region[#@](\d+)\)", protocol)
    assert regions
    # The explicit click-through regions must remain empty; no rectangle is added.
    assert any(not re.search(rf"wl_region[#@]{region}\.add\(", protocol) for region in regions)


async def test_native_binding_registration_is_reversible():
    before = await hypr_json("binds")
    if any(b.get("description", "").startswith("Caelum") for b in before):
        pytest.skip("Preserving another Caelum service's active shortcuts")
    bindings = Bindings("SUPER + ALT + V")
    try:
        await bindings.install()
        await bindings.active(True)
        await bindings.active(False)
        current = await hypr_json("binds")
        assert len(current) == len(before) + 3
        assert any(b["key"] == "V" and b["modmask"] == 72 for b in current)
    finally:
        await bindings.remove()
    assert await hypr_json("binds") == before


async def test_native_service_cancellation_without_api_upload(tmp_path):
    if (runtime_dir() / "control.sock").exists():
        pytest.skip("Another Caelum daemon is already running")
    env = os.environ.copy()
    env["GROQ_API_KEY"] = "synthetic-unused-key"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[app]\nminimum_recording_ms=2000\n[stt]\nbase_url="http://127.0.0.1:9"\n[cleanup]\nmodel=""\n'
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "caelum.cli",
        "--config",
        str(config_path),
        "serve",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    async def control(action):
        reader, writer = await asyncio.open_unix_connection(str(runtime_dir() / "control.sock"))
        writer.write(json.dumps({"action": action, "token": "native-cancel"}).encode() + b"\n")
        await writer.drain()
        result = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()
        return result

    try:
        line = await asyncio.wait_for(process.stdout.readline(), 8)
        assert b"Caelum ready" in line, (await process.stderr.read()).decode()
        assert (await control("start")).get("ok")
        await asyncio.sleep(0.08)
        assert (await control("cancel")).get("ok")
        state = await control("status")
        assert state["state"] == "hidden"
        assert state["pending_audio"] is False
        assert state["metrics"] == []
    finally:
        if process.returncode is None:
            process.terminate()
        with suppress(TimeoutError):
            await asyncio.wait_for(process.wait(), 5)
        if process.returncode is None:
            process.kill()
            await process.wait()
    assert process.returncode == 0
    assert not (runtime_dir() / "control.sock").exists()
    assert not any(b.get("description", "").startswith("Caelum") for b in await hypr_json("binds"))


async def test_native_visible_insertion_in_disposable_gtk_field():
    from pathlib import Path

    from caelum.linux import command, insert, wayland_env

    # Preserve the previous text clipboard entirely in memory; never print it.
    types = await asyncio.create_subprocess_exec(
        "wl-paste",
        "--list-types",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    mime_types, _ = await types.communicate()
    if types.returncode == 0 and not any(t.startswith(b"text/") for t in mime_types.splitlines()):
        pytest.skip("Preserving the existing non-text clipboard")
    clipboard = await asyncio.create_subprocess_exec(
        "wl-paste",
        "--type",
        "text",
        "--no-newline",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    previous_clipboard, _ = await clipboard.communicate()
    if clipboard.returncode:
        previous_clipboard = None
    before = await hypr_json("activewindow")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("native_target.py")),
        env=wayland_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 5) == b"ready\n"
        for _ in range(50):
            clients = await hypr_json("clients")
            window = next((w for w in clients if w.get("pid") == process.pid), None)
            if window:
                break
            await asyncio.sleep(0.02)
        assert window
        await command(
            "hyprctl",
            "dispatch",
            "hl.dsp.focus({window=" + json.dumps("address:" + window["address"]) + "})",
        )
        target = await target_at_press(window["address"])
        assert await insert("Caelum insertion check — 42.", target)
        assert await asyncio.wait_for(process.stdout.readline(), 3) == b"visible-match\n"
    finally:
        if process.returncode is None:
            process.terminate()
        await process.wait()
        if previous_clipboard is not None:
            await command("wl-copy", "--type", "text/plain;charset=utf-8", data=previous_clipboard)
        else:
            await command("wl-copy", "--clear")
        if before.get("address"):
            await command(
                "hyprctl",
                "dispatch",
                "hl.dsp.focus({window=" + json.dumps("address:" + before["address"]) + "})",
            )
