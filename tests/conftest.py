"""Never read a developer's real credentials or history during unit tests."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path, monkeypatch, request):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    if os.environ.get("CAELUM_NATIVE_TESTS") == "1" and request.node.path.name == "test_native.py":
        # Session integration must use the real compositor socket while config,
        # credentials and history remain isolated. Ordinary tests stay hermetic.
        if not os.environ.get("XDG_RUNTIME_DIR"):
            pytest.skip("No active desktop runtime is available")
        return
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
