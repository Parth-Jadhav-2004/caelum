"""Manual testing-release discovery never grants installation trust."""
import json

import httpx
import pytest
from caelum import updates


@pytest.fixture
def discovery(monkeypatch):
    info = {"version": "0.4.1", "target": "arch", "python": "3.14"}
    monkeypatch.setattr(updates, "installed", lambda: info)
    monkeypatch.setattr(updates, "compatible", lambda _: True)

    def serve(releases, status=200, source_date="2026-11-16T10:00:00Z"):
        def respond(request):
            if "/git/commits/" in request.url.path:
                return httpx.Response(200, json={
                    "sha": request.url.path.rsplit("/", 1)[1],
                    "committer": {"date": source_date},
                })
            if request.url.path.endswith("/candidate.json"):
                return httpx.Response(200, json={
                    "schema": 1, "version": "0.4.1", "sha": "a" * 40,
                })
            assert str(request.url) == (
                "https://api.github.com/repos/Parth-Jadhav-2004/caelum/releases?per_page=20"
            )
            return httpx.Response(status, content=json.dumps(releases))
        monkeypatch.setattr(updates, "network_client", lambda _: httpx.Client(
            transport=httpx.MockTransport(respond), headers={"Accept-Encoding": "identity"},
        ))

    return info, serve


def preview(tag="v0.4.1-rc.2", source="a" * 40):
    return {
        "draft": False, "prerelease": True, "tag_name": tag,
        "target_commitish": source, "published_at": "2026-11-17T10:00:00Z",
        "assets": [{"name": f"caelum-{tag[1:].split('-')[0]}-1-x86_64.pkg.tar.zst"}],
    }


def test_detects_new_candidate_with_same_package_version(discovery, monkeypatch):
    _, serve = discovery
    serve([preview(), {"draft": False, "prerelease": False, "tag_name": "v0.4.0"}])
    monkeypatch.setattr(updates, "stage", lambda _: pytest.fail("unsigned install"))
    assert updates.check_testing() == {"version": "0.4.1-rc.2", "installed": False}


def test_identifies_the_installed_source_instead_of_offering_a_reinstall(discovery):
    info, serve = discovery
    info.update(source="a" * 40, source_date=9999999999)
    serve([preview()])
    assert updates.check_testing() == {"version": "0.4.1-rc.2", "installed": True}


def test_chooses_candidate_number_instead_of_api_order(discovery):
    _, serve = discovery
    serve([preview("v0.4.1-rc.2"), preview("v0.4.1-rc.10"), preview("v0.3.9-rc.99")])
    assert updates.check_testing()["version"] == "0.4.1-rc.10"


@pytest.mark.parametrize("reason", ["stable", "draft", "old", "newer-install", "wrong-target"])
def test_does_not_offer_an_inapplicable_candidate(discovery, reason):
    info, serve = discovery
    item = preview()
    releases = [item]
    if reason == "stable":
        releases.append({"draft": False, "prerelease": False, "tag_name": "v0.4.1"})
    elif reason == "draft":
        item["draft"] = True
    elif reason == "old":
        info["version"] = "0.4.2"
    elif reason == "newer-install":
        info.update(source="b" * 40, source_date=1795000000)
    else:
        info["target"] = "debian-12"
    serve(releases)
    assert updates.check_testing() is None


@pytest.mark.parametrize("payload,status", [([], 503), ({"message": "rate limit"}, 403), ({}, 200)])
def test_network_and_metadata_errors_do_not_report_up_to_date(discovery, payload, status):
    _, serve = discovery
    serve(payload, status)
    with pytest.raises(RuntimeError, match="Could not check testing releases"):
        updates.check_testing()


@pytest.mark.parametrize("target", ["a" * 40, "main"])
def test_delayed_publication_cannot_offer_older_same_version_source(discovery, target):
    info, serve = discovery
    info.update(source="b" * 40, source_date=1794910000)
    item = preview(source=target)
    item["published_at"] = "2026-11-20T10:00:00Z"
    serve([item], source_date="2026-11-16T10:00:00Z")
    assert updates.check_testing() is None


def test_newer_same_version_source_is_offered_based_on_commit_provenance(discovery):
    info, serve = discovery
    info.update(source="b" * 40, source_date=1794800000)
    item = preview()
    item["published_at"] = "2026-11-01T10:00:00Z"
    serve([item], source_date="2026-11-17T10:00:00Z")
    assert updates.check_testing() == {"version": "0.4.1-rc.2", "installed": False}


def test_semantically_newer_package_is_not_hidden_by_source_date(discovery):
    info, serve = discovery
    info.update(source="b" * 40, source_date=9999999999)
    serve([preview("v0.4.2-rc.1")])
    assert updates.check_testing() == {"version": "0.4.2-rc.1", "installed": False}
