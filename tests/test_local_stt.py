import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from caelum.config import Config, load, save
from caelum.local_stt import transcribe
from caelum.providers import ProviderError, Providers
from caelum.quality import cleanup_prompt


def local_config(tmp_path, body):
    config = Config()
    config.stt.engine = "local"
    model = tmp_path / "model.bin"
    model.write_bytes(b"model")
    binary = tmp_path / "whisper-cli"
    binary.write_text(f"#!{sys.executable}\n" + body)
    binary.chmod(0o700)
    config.stt.local_binary = str(binary)
    config.stt.local_model_path = str(model)
    return config


async def test_local_uses_memory_wav_and_vocabulary_without_network(tmp_path):
    config = local_config(tmp_path, '''import sys
from pathlib import Path
args = sys.argv
assert Path(args[args.index('-f') + 1]).read_bytes().startswith(b'RIFF')
assert args[args.index('--prompt') + 1] == 'Caelum, Omarchy, Hyprland'
print('Hello Caelum')
''')
    config.cleanup.model = "cloud-model"
    client = AsyncMock()
    provider = Providers(config, client=client, credential_resolver=lambda _: pytest.fail("credential lookup"))
    assert await provider.models(config.stt) == [config.stt.model]
    result = await provider.stt(b'\x00\x00' * 1600)
    assert result.text == "Hello Caelum"
    assert await provider.cleanup(result.text) == ("Hello Caelum", False)
    client.post.assert_not_called()
    client.get.assert_not_called()
    assert provider.metrics["uploaded_audio_bytes"] == 0


async def test_local_missing_model_and_failure_are_sanitized(tmp_path):
    config = local_config(tmp_path, "import sys\nprint('private text')\nsys.exit(1)\n")
    with pytest.raises(ProviderError, match="Local transcription failed"):
        await transcribe(config.stt, b'\x00\x00' * 100)
    Path(config.stt.local_model_path).unlink()
    with pytest.raises(ProviderError, match="GGML model"):
        await transcribe(config.stt, b'')


async def test_cancel_terminates_local_process(tmp_path):
    pid_file = tmp_path / "pid"
    config = local_config(tmp_path, f"import os, time\nfrom pathlib import Path\nPath({str(pid_file)!r}).write_text(str(os.getpid()))\ntime.sleep(60)\n")
    task = asyncio.create_task(transcribe(config.stt, b'\x00\x00' * 100))
    for _ in range(200):
        if pid_file.exists():
            break
        await asyncio.sleep(0.01)
    assert pid_file.exists()
    pid = int(pid_file.read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_new_settings_roundtrip_and_legacy_style(tmp_path):
    config = Config()
    config.stt.vocabulary = "Acme, Zoë\nPostgreSQL"
    config.cleanup.style = "email"
    path = tmp_path / "config.toml"
    save(config, path)
    assert load(path) == config
    path.write_text('[cleanup]\nreasoning_effort = "high"\n')
    assert load(path).cleanup.style == "thorough"
    assert len({cleanup_prompt(style) for style in ("light", "thorough", "email", "casual", "code")}) == 5
