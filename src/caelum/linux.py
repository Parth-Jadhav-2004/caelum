"""Native Hyprland Lua bindings and target-addressed paste; no X11 hooks."""

import asyncio
import json
import os
import re
import shlex
import shutil
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


async def command(*args, data=None, timeout=3):
    process = await asyncio.create_subprocess_exec(
        *map(str, args),
        stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _ = await asyncio.wait_for(process.communicate(data), timeout)
    except BaseException:
        process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed")
    return out.decode().strip()


async def hypr_json(name):
    return json.loads(await command("hyprctl", "-j", name))


def runtime_dir():
    root = os.environ.get("XDG_RUNTIME_DIR")
    if not root:
        raise RuntimeError("XDG_RUNTIME_DIR is required; run inside your Linux desktop login")
    path = Path(root) / "caelum"
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise RuntimeError("Unsafe runtime directory")
    path.chmod(0o700)
    return path


@dataclass
class Target:
    address: str
    pid: int
    monitor: int
    output: str
    terminal: bool = False


async def target_at_press(address=None):
    clients, monitors = await asyncio.gather(hypr_json("clients"), hypr_json("monitors"))
    window = (
        next((w for w in clients if w["address"] == address), {})
        if address
        else await hypr_json("activewindow")
    )
    monitor_id = window.get("monitor", next((m["id"] for m in monitors if m.get("focused")), -1))
    output = next((m["name"] for m in monitors if m["id"] == monitor_id), "")
    tags = window.get("tags", [])
    terminal = any(t.rstrip("*") == "terminal" for t in tags)
    return Target(window.get("address", ""), window.get("pid", -1), monitor_id, output, terminal)


async def notify(message, actions=False):
    # CLI recovery actions are always available; notification actions are opt-in supported by mako.
    args = ["notify-send", "--app-name=Caelum", "--expire-time=5000"]
    args += ["Caelum", message]
    try:
        await command(*args)
    except (RuntimeError, FileNotFoundError, TimeoutError):
        pass


async def insert(text, target):
    await command("wl-copy", "--type", "text/plain;charset=utf-8", data=text.encode())
    current = await hypr_json("activewindow")
    if (
        not target.address
        or current.get("address") != target.address
        or current.get("pid") != target.pid
    ):
        return False
    if not re.fullmatch(r"0x[0-9a-fA-F]+", target.address):
        return False
    # Addressed dispatch prevents a focus race from pasting into a different app.
    mods, key = ("SHIFT", "Insert") if target.terminal else ("CTRL", "V")

    def key_state(state):
        return (
            "hl.dsp.send_key_state({mods="
            + json.dumps(mods)
            + ",key="
            + json.dumps(key)
            + ",state="
            + json.dumps(state)
            + ",window="
            + json.dumps("address:" + target.address)
            + "})"
        )

    down = await command("hyprctl", "dispatch", key_state("down"))
    try:
        await asyncio.sleep(0.05)
    finally:
        # Explicit release runs on cancellation, avoiding sticky synthetic keys.
        up = await command("hyprctl", "dispatch", key_state("up"))
    return down == "ok" and up == "ok"


def shortcut_keys(hotkey):
    pieces = [piece.strip() for piece in hotkey.split("+")]
    masks = {"SUPER": 64, "ALT": 8, "CTRL": 4, "SHIFT": 1}
    key_names = {"SUPER": "Super", "ALT": "Alt", "CTRL": "Control", "SHIFT": "Shift"}
    modifier_only = all(piece in masks for piece in pieces)
    if modifier_only:
        starts = [
            (
                " + ".join([*(other for other in pieces if other != modifier), key]),
                key,
                sum(masks[other] for other in pieces if other != modifier),
            )
            for modifier in pieces
            for key in (key_names[modifier] + "_L", key_names[modifier] + "_R")
        ]
    else:
        starts = [(hotkey, pieces[-1], sum(masks[modifier] for modifier in pieces[:-1]))]
    return starts, modifier_only


class Bindings:
    def __init__(self, hotkey):
        self.hotkey = hotkey
        self.installed = False

    async def install(self):
        if (await hypr_json("status")).get("configProvider") != "lua":
            raise RuntimeError("Caelum currently requires Hyprland's Lua configuration API")
        starts, modifier_only = shortcut_keys(self.hotkey)
        binds = await hypr_json("binds")
        if any(
            b["key"].upper() == key.upper() and b["modmask"] == mask
            for _, key, mask in starts
            for b in binds
        ):
            raise RuntimeError(f"Hotkey collision: {self.hotkey}; choose another in config")
        base = shlex.join([sys.executable, "-m", "caelum.cli", "control"])
        # Lua owns the held flag: no autorepeat sessions and release works in either modifier order.
        # Exact binding handles are removed; existing user bindings are never unbound.
        code = f"""
        if _caelum then for _,b in ipairs(_caelum.binds) do b:remove() end end
        _caelum={{binds={{}}, held=false, token=0, prefix={json.dumps(uuid.uuid4().hex)}}}
        local c=_caelum
        local function send(action, suffix)
          hl.dispatch(hl.dsp.exec_cmd({json.dumps(base)} .. " " .. action .. " " .. c.prefix .. c.token .. (suffix or "")))
        end
        c.escape=hl.bind("Escape", function() c.held=false; send("cancel") end,
          {{description="Caelum cancel", ignore_mods=true}})
        c.escape:set_enabled(false)
        table.insert(c.binds,c.escape)
        local function start()
          if c.held then return end
          c.held=true; c.token=c.token+1
          c.escape:set_enabled(true)
          local w=hl.get_active_window()
          send("start", " " .. (w and w.address or "none"))
        end
        local function stop()
          if c.held then c.held=false; send("stop") end
        end
        """
        for shortcut, key, _ in starts:
            code += f"""
            table.insert(c.binds,hl.bind({json.dumps(shortcut)}, start,
              {{description="Caelum hold to dictate", non_consuming={str(modifier_only).lower()}}}))
            table.insert(c.binds,hl.bind({json.dumps(key)}, stop,
              {{release=true,ignore_mods=true,non_consuming=true,transparent=true,
                description="Caelum release"}}))
            """
        out = await command("hyprctl", "eval", code)
        if out != "ok":
            raise RuntimeError("Hyprland rejected Caelum bindings")
        self.installed = True

    async def active(self, enabled):
        await command(
            "hyprctl",
            "eval",
            f"if _caelum then _caelum.escape:set_enabled({str(enabled).lower()}) end",
        )

    async def remove(self):
        if self.installed:
            await command(
                "hyprctl",
                "eval",
                "if _caelum then for _,b in ipairs(_caelum.binds) do b:remove() end; _caelum=nil end",
            )
            self.installed = False


def wayland_env():
    # Layer Shell must interpose libwayland before GTK loads (see upstream linking.md).
    import ctypes.util

    library = ctypes.util.find_library("gtk4-layer-shell")
    if not library:
        raise RuntimeError("Install gtk4-layer-shell")
    env = os.environ.copy()
    env["GDK_BACKEND"] = "wayland"
    env["LD_PRELOAD"] = library + (" " + env["LD_PRELOAD"] if env.get("LD_PRELOAD") else "")
    return env


async def session_locked():
    # Omarchy's lock plugin exposes the requested state before secure lock mapping.
    if not shutil.which("omarchy-shell"):
        from .portable import session_locked as logind_locked

        return await logind_locked()
    value = await command("omarchy-shell", "lock", "isLocked", timeout=2)
    if value not in ("true", "false"):
        raise RuntimeError("Cannot establish Omarchy lock state")
    return value == "true"


async def recovery_notification(core, session, seconds):
    try:
        action = await command(
            "notify-send",
            "--app-name=Caelum",
            "--wait",
            f"--expire-time={int(seconds * 1000)}",
            "--action=retry=Retry",
            "--action=cancel=Cancel",
            "Caelum · dictation paused",
            "Retry or cancel. CLI: caelum control retry / cancel. Audio expires in memory.",
            timeout=seconds + 1,
        )
        if action in ("retry", "cancel") and session == core.session:
            await core.handle(action)
    except (OSError, RuntimeError, TimeoutError):
        if session == core.session and core.pcm is not None:
            await notify(
                "Dictation paused. Run caelum control retry or caelum control cancel before audio expires."
            )
