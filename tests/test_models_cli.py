import json
import sys
from unittest.mock import AsyncMock, Mock

import pytest
from caelum import cli, models


def test_models_list_does_not_load_config_or_create_http_client(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["caelum", "models", "list"])
    monkeypatch.setattr(cli, "load", lambda _: pytest.fail("Unneeded config read"))
    monkeypatch.setattr("httpx.AsyncClient", lambda **_: pytest.fail("Unneeded HTTP client"))
    cli.main()
    output = capsys.readouterr().out
    assert all(model["id"] in output for model in models.catalog()["models"])


def test_download_dispatch_and_required_id(monkeypatch, tmp_path):
    download = AsyncMock(return_value=tmp_path / "parakeet-v3")
    monkeypatch.setattr(models.ModelManager, "download", download)
    monkeypatch.setattr(sys, "argv", ["caelum", "models", "download", "parakeet-v3"])
    cli.main()
    download.assert_awaited_once_with("parakeet-v3")
    monkeypatch.setattr(sys, "argv", ["caelum", "models", "download"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_cli_verification_failure_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["caelum", "models", "verify", "parakeet-v3"])
    monkeypatch.setattr(models, "verify", Mock(return_value={"ok": False, "bad_files": ["tokens.txt"]}))
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().out)["bad_files"] == ["tokens.txt"]


def test_local_benchmark_requires_a_model(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["caelum", "benchmark", "manifest.json", "--engine", "local"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_local_benchmark_dispatch_is_explicit(monkeypatch):
    run = AsyncMock()
    monkeypatch.setattr("caelum.benchmark.local_benchmark", run)
    monkeypatch.setattr(sys, "argv", [
        "caelum", "benchmark", "manifest.json", "--engine", "local",
        "--model", "parakeet-110m", "--threads", "2", "--repeat", "1",
    ])
    cli.main()
    assert run.await_args.args[-2:] == ("parakeet-110m", 2)


def test_online_benchmark_rejects_local_flags(monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "caelum", "benchmark", "manifest.json", "--model", "parakeet-v3",
    ])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


@pytest.mark.parametrize("model_id,supported,ready", [("", True, False),
                                                    ("parakeet-110m", False, False),
                                                    ("parakeet-110m", True, True)])
async def test_local_doctor_never_uses_retired_executable_path(monkeypatch, capsys, model_id, supported, ready):
    from caelum.config import Config
    from caelum.hardware import Hardware

    config = Config()
    config.stt.engine, config.stt.local_model = "local", model_id
    monkeypatch.setattr("caelum.portable.backend_name", lambda _: "portable")
    monkeypatch.setattr("caelum.portable.session_locked", AsyncMock(return_value=False))
    monkeypatch.setattr("caelum.linux.command", AsyncMock(return_value=""))
    monkeypatch.setattr("caelum.pulse.resolve", lambda _: "fake-device")
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/fake/binary")
    monkeypatch.setattr("caelum.hardware.detect", lambda _: Hardware(arch="x86_64", avx2=supported))
    monkeypatch.setattr(models, "installed", lambda _: True)
    monkeypatch.setattr(models.importlib.util, "find_spec", lambda _: True)
    monkeypatch.setattr("caelum.credentials.get", lambda _: pytest.fail("Credential lookup in local doctor"))
    await cli.doctor(config)
    checks = json.loads(capsys.readouterr().out)["checks"]
    assert checks["local_models_supported"] is supported
    assert checks["local_transcription_ready"] is ready
