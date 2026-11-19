"""Release publication must not offer missing, ambiguous, or unchecked packages."""

import importlib.util
import io
import urllib.error
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "website_release", Path(__file__).resolve().parents[1] / "scripts/update-website-release.py"
)
website = importlib.util.module_from_spec(spec)
spec.loader.exec_module(website)

FILE = "caelum_0.4.2-1_ubuntu-24.04_amd64.deb"
BASE = f"{website.GITHUB}/releases/download/v0.4.2/"


def release(names=(FILE,)):
    return {
        "tag_name": "v0.4.2",
        "assets": [
            {"name": name, "size": 123, "browser_download_url": BASE + name}
            for name in (*names, "SHA256SUMS", "update.json", "update.json.sig")
        ],
    }


def reader(missing=None, checksummed=True):
    def read(url, **_kwargs):
        if url.endswith(missing or "NEVER"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        body = (("0" * 64 + "  " + FILE + "\n") if checksummed else "").encode()
        response = io.BytesIO(body)
        response.status = 200
        return response

    return read


def test_published_only():
    data = website.build_manifest(release(), reader())
    assert [item["id"] for item in data["packages"]] == ["ubuntu-2404"]
    assert data["packages"][0]["sha256"] == "0" * 64
    assert data["version"] == "0.4.2"


def test_missing_target_is_omitted():
    arch = "caelum-0.4.2-1-x86_64.pkg.tar.zst"

    def read(url, **kwargs):
        if url.endswith("SHA256SUMS"):
            response = io.BytesIO(("0" * 64 + "  " + FILE + "\n" + "0" * 64 + "  " + arch).encode())
            response.status = 200
            return response
        return reader(missing=arch)(url, **kwargs)

    data = website.build_manifest(release((FILE, arch)), read)
    assert len(data["packages"]) == 1
    assert data["packages"][0]["id"] == "ubuntu-2404"


@pytest.mark.parametrize("missing", [FILE, "SHA256SUMS", "update.json", "update.json.sig"])
def test_missing_required_assets_abort(missing):
    with pytest.raises((ValueError, urllib.error.HTTPError)):
        website.build_manifest(release(), reader(missing=missing))


def test_unsigned_or_unstable_data_aborts():
    with pytest.raises(ValueError, match="SHA256SUMS"):
        website.build_manifest(release(), reader(checksummed=False))
    for override in ({"draft": True}, {"prerelease": True}, {"tag_name": "v0.5.0-beta.1"}):
        with pytest.raises(ValueError):
            website.build_manifest(release() | override, reader())
    data = release()
    data["assets"][0]["browser_download_url"] = "https://example.com/package.deb"
    with pytest.raises(ValueError, match="Unexpected asset URL"):
        website.build_manifest(data, reader())
