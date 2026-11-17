"""Lightweight hotkey client; heavy capture/UI imports occur only in the daemon."""

import argparse
import asyncio
import json
import os
import shutil
import socket
import sys
from pathlib import Path

from .config import config_path, load


def control(action, token=None, address=None):
    root = os.environ.get("XDG_RUNTIME_DIR")
    if not root:
        raise RuntimeError("Run inside a Linux desktop login")
    payload = {"action": action, "token": token or ""}
    if address:
        payload["address"] = address
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(Path(root) / "caelum/control.sock"))
        client.sendall(json.dumps(payload).encode() + b"\n")
        reply = client.makefile("r").readline(65536)
        result = json.loads(reply)
        if "error" in result:
            raise RuntimeError(result["error"])
        if action == "status":
            print(json.dumps(result, indent=2))
        return result


async def model_command(args, parser):
    from .models import ModelManager, catalog, installed, models_dir, pin, verify

    if args.action == "list":
        if args.id:
            parser.error("models list does not accept an id")
        for model in catalog()["models"]:
            state = "installed" if installed(model["id"]) else "not installed"
            print(f"{model['id']}\t{model['label']}\t{model['download_bytes'] / 1e6:.0f} MB\t{state}")
        return
    if not args.id:
        parser.error(f"models {args.action} requires a catalog id")
    if args.action == "pin":
        print(json.dumps(await pin(args.id), indent=2))
        return
    manager = ModelManager()
    if args.action == "download":
        print(f"Downloading {args.id}; interrupt to pause, run again to resume.", file=sys.stderr)
        print(await manager.download(args.id))
    elif args.action == "verify":
        result = await asyncio.to_thread(verify, args.id)
        print(json.dumps(result, indent=2))
        if not result["ok"]:
            raise RuntimeError("Speech model files need attention")
    elif args.action == "remove":
        print(json.dumps({"freed_bytes": manager.remove(args.id), "stored_in": str(models_dir())}))


async def doctor(config):
    from .linux import command, hypr_json, wayland_env
    from .portable import SHORTCUTS, backend_name, session_locked

    backend = backend_name(config)
    native = backend == "hyprland"
    checks = {}
    binaries = (
        ("hyprctl", "wl-copy", "notify-send", "gdbus")
        if native
        else (
            "notify-send",
            "gdbus",
            "loginctl",
        )
    )
    for binary in binaries:
        checks[binary] = bool(shutil.which(binary))
    checks["desktop_session"] = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))
    checks["runtime_directory"] = bool(os.environ.get("XDG_RUNTIME_DIR"))
    if config.stt.engine == "local":
        import importlib.util

        from .hardware import detect, local_support
        from .models import EXTRA_MODULES, get_model, installed

        checks["local_models_supported"] = local_support(detect(config)) is None
        ready = bool(config.stt.local_model) and installed(config.stt.local_model)
        if ready:
            extra = get_model(config.stt.local_model)["requires_extra"] or "local"
            ready = importlib.util.find_spec(EXTRA_MODULES[extra]) is not None
        checks["local_transcription_ready"] = ready and checks["local_models_supported"]
    for name, provider in (("stt", config.stt), ("cleanup", config.cleanup)):
        if config.stt.engine == "local":
            continue
        if name == "cleanup" and not config.cleanup.model:
            continue
        from .credentials import get as credential

        checks[f"{name}_credential_present"] = bool(
            await asyncio.to_thread(credential, provider.key_env)
        )
    try:
        if native:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "caelum.hud",
                "--check",
                env=wayland_env(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(process.communicate(), 5)
            checks["gtk4_layer_shell"] = process.returncode == 0
        else:
            checks["tauri_desktop"] = bool(shutil.which("caelum-desktop"))
            await session_locked()
            checks["session_lock_feedback"] = True
    except (ImportError, OSError, ValueError, RuntimeError, TimeoutError):
        checks["desktop_integration"] = False
    try:
        from .pulse import resolve

        source = resolve(config.app.microphone)
        if source is not None:
            checks["input_device"] = True
        else:
            import sounddevice as sd

            checks["input_device"] = bool(sd.query_devices(config.app.microphone, "input"))
            sd.check_input_settings(
                device=config.app.microphone, channels=1, samplerate=16000, dtype="int16"
            )
        checks["microphone_16khz"] = True
    except Exception:
        checks["microphone_16khz"] = False
    capabilities = {"automatic_paste": native, "manual_recording": not native}
    if native:
        try:
            checks["hyprland_lua"] = (await hypr_json("status")).get("configProvider") == "lua"
            checks["hyprland_config_clean"] = not bool(await command("hyprctl", "configerrors"))
            from .linux import shortcut_keys

            starts, _ = shortcut_keys(config.app.hotkey)
            binds = await hypr_json("binds")
            checks["hotkey_available"] = not any(
                b["key"].upper() == key.upper()
                and b["modmask"] == mask
                and not b.get("description", "").startswith("Caelum")
                for _, key, mask in starts
                for b in binds
            )
        except (OSError, ValueError, RuntimeError, TimeoutError):
            checks["hyprland_lua"] = False
    else:
        try:
            xml = await command(
                "gdbus",
                "introspect",
                "--session",
                "--dest",
                "org.freedesktop.portal.Desktop",
                "--object-path",
                "/org/freedesktop/portal/desktop",
                "--xml",
            )
            capabilities["global_shortcuts_portal"] = SHORTCUTS in xml
        except (OSError, RuntimeError, TimeoutError):
            capabilities["global_shortcuts_portal"] = False
    print(
        json.dumps({"backend": backend, "checks": checks, "capabilities": capabilities}, indent=2)
    )
    return 0 if all(checks.values()) else 1


def main():
    parser = argparse.ArgumentParser(description="Caelum · private dictation for Linux desktops")
    parser.add_argument("--config", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="Start the native HUD and dictation service")
    sub.add_parser("app", help="Open the native desktop application")
    ctrl = sub.add_parser("control", help="Send a local daemon command")
    ctrl.add_argument(
        "action",
        choices=[
            "start",
            "stop",
            "toggle",
            "cancel",
            "retry",
            "status",
            "reload",
            "pause",
            "resume",
            "shutdown",
        ],
    )
    ctrl.add_argument("token", nargs="?")
    ctrl.add_argument("address", nargs="?")
    sub.add_parser(
        "doctor", help="Check local dependencies, microphone, configuration, credentials"
    )
    sub.add_parser("devices", help="List microphones")
    sub.add_parser("init", help="Create a config file without overwriting an existing one")
    models = sub.add_parser("models", help="Manage local models or verify provider model identifiers")
    models.add_argument("action", choices=["stt", "cleanup", "list", "download", "remove", "verify", "pin"])
    models.add_argument("id", nargs="?")
    bench = sub.add_parser("benchmark", help="Benchmark a user-provided WAV corpus (online uploads)")
    bench.add_argument("manifest", type=Path)
    bench.add_argument("--repeat", type=int, default=3)
    bench.add_argument("--output", default="benchmark-results.json")
    bench.add_argument("--engine", choices=["online", "local"], default="online")
    bench.add_argument("--model", help="Pinned local catalog id (required with --engine local)")
    bench.add_argument("--threads", type=int, default=0, help="Local CPU threads; 0 selects automatically")
    replay = sub.add_parser(
        "hud-demo", help="Replay HUD states without microphone, network, or insertion"
    )
    replay.add_argument("--seconds", type=float, default=1.2)
    args = parser.parse_args()
    try:
        if args.command == "control":
            control(args.action, args.token, args.address)
            return
        if args.command == "models" and args.action not in ("stt", "cleanup"):
            asyncio.run(model_command(args, parser))
            return
        if args.command == "models" and args.id:
            parser.error("models stt/cleanup does not accept an id")
        config = load(args.config)
        if args.command == "init":
            path = args.config or config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            example = Path(__file__).with_name("config.example.toml")
            if not example.exists():
                example = Path(__file__).resolve().parents[2] / "config.example.toml"
            with path.open("x") as file:
                file.write(example.read_text())
            print(path)
        elif args.command == "devices":
            from .desktop_services import microphones

            for label, device in microphones():
                print(f"{device}\t{label}")
        elif args.command == "doctor":
            sys.exit(asyncio.run(doctor(config)))
        elif args.command == "serve":
            from .onboarding import privacy
            from .service import serve

            print(privacy(config), file=sys.stderr)
            asyncio.run(serve(config, args.config))
        elif args.command == "app":
            from .desktop import run

            run(args.config)
        elif args.command == "models":

            async def models():
                from .providers import Providers

                provider = Providers(config)
                try:
                    for name in await provider.models(getattr(config, args.action)):
                        print(name)
                finally:
                    await provider.client.aclose()

            asyncio.run(models())
        elif args.command == "benchmark":
            if not 1 <= args.repeat <= 20:
                parser.error("repeat must be between 1 and 20")
            if args.engine == "local":
                if not args.model:
                    parser.error("--model is required with --engine local")
                from .benchmark import local_benchmark

                asyncio.run(local_benchmark(
                    config, args.manifest, args.repeat, args.output, args.model, args.threads
                ))
            else:
                if args.model or args.threads:
                    parser.error("--model and --threads require --engine local")
                if config.stt.engine == "local":
                    parser.error("Online benchmark requires an online transcription config")
                from .benchmark import benchmark

                asyncio.run(benchmark(config, args.manifest, args.repeat, args.output))
        elif args.command == "hud-demo":

            async def demo():
                from .linux import target_at_press
                from .orchestrator import HUD

                hud = HUD(config.app)
                target = await target_at_press()
                await hud.start()
                try:
                    for seq, state in enumerate(
                        (
                            "starting",
                            "listening",
                            "recording",
                            "processing",
                            "refining",
                            "success",
                            "error",
                            "copied",
                            "no_speech",
                            "hidden",
                        )
                    ):
                        # Zero waveform in a state replay; never simulate microphone input.
                        await hud.emit(
                            {
                                "session_id": "demo",
                                "sequence": seq,
                                "state": state,
                                "elapsed_ms": 12000,
                                "level": 0,
                                "history": [0] * 17,
                                "output": target.output,
                                "error_code": "network" if state == "error" else "",
                            }
                        )
                        await asyncio.sleep(max(0.2, min(args.seconds, 5)))
                finally:
                    await hud.close()

            asyncio.run(demo())
    except (OSError, RuntimeError, ValueError) as error:
        # Provider errors are sanitized before they reach this boundary.
        print(f"Caelum: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
