import io
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from caelum import cuda_runtime, local_stt
from caelum.providers import ProviderError

GPU = b"VerifyEachNodeIsAssignedToAnEp]  Node(s) placed on [CUDAExecutionProvider]. Number of nodes: 42\n"


@pytest.mark.parametrize("model_logs", [
    b"Available providers: CUDAExecutionProvider, CPUExecutionProvider\n",
    GPU + b"Available providers: CUDAExecutionProvider, CPUExecutionProvider, . Fallback to cpu\n",
    b"VerifyEachNodeIsAssignedToAnEp]  All nodes placed on [CPUExecutionProvider]. Number of nodes: 42\n",
    b"Traceback: private model path\n",
])
def test_successful_preflight_cannot_mask_cpu_only_model(model_logs):
    worker = SimpleNamespace(stderr=io.BytesIO(
        GPU + b"CAELUM_PROVIDER_READY\n" + model_logs + b"CAELUM_MODEL_READY\n"))
    cuda_runtime.confirm_placement(worker, b"CAELUM_PROVIDER_READY")
    with pytest.raises(ProviderError, match="Auto or CPU") as exc:
        cuda_runtime.confirm_placement(worker, b"CAELUM_MODEL_READY")
    assert exc.value.kind == "local_setup" and "private" not in str(exc.value)


def test_missing_component_respects_explicit_device(tmp_path, monkeypatch):
    monkeypatch.setattr(cuda_runtime, "runtime_dir", lambda: tmp_path)
    cpu = Mock()
    model = {"runtime": "sherpa-transducer"}
    monkeypatch.setitem(local_stt.ADAPTERS, model["runtime"], cpu)
    with pytest.raises(ProviderError, match="install-nvidia") as exc:
        local_stt.runtime_adapter(model, tmp_path, 2, "", "", device="gpu")
    assert ("Windows" if os.name == "nt" else "Linux") in str(exc.value)
    cpu.assert_not_called()
    assert local_stt.runtime_adapter(model, tmp_path, 2, "", "", device="auto") is cpu.return_value
    monkeypatch.setattr(cuda_runtime, "runtime_dir", lambda: pytest.fail("CPU probed CUDA"))
    assert local_stt.runtime_adapter(model, tmp_path, 2, "", "", device="cpu") is cpu.return_value
