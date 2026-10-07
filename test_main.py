"""Run with:  pytest -q"""

import csv
import json

import pytest
import requests

import main


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(main.time, "sleep", lambda s: None)


def test_fetch_success(monkeypatch):
    monkeypatch.setattr(
        main.requests, "get", lambda *a, **k: FakeResponse(200, {"login": "octocat"})
    )
    assert main.fetch_profile("octocat")["login"] == "octocat"


def test_404_is_not_retried(monkeypatch):
    calls = []

    def fake_get(*a, **k):
        calls.append(1)
        return FakeResponse(404)

    monkeypatch.setattr(main.requests, "get", fake_get)
    with pytest.raises(main.UserNotFoundError):
        main.fetch_profile("nobody-here")
    assert len(calls) == 1


def test_timeout_retries_three_times_then_gives_up(monkeypatch):
    calls = []

    def fake_get(*a, **k):
        calls.append(1)
        raise requests.Timeout()

    monkeypatch.setattr(main.requests, "get", fake_get)
    with pytest.raises(main.FetchError):
        main.fetch_profile("octocat")
    assert len(calls) == 3


def test_recovers_after_failures(monkeypatch):
    responses = iter(
        [requests.ConnectionError(), FakeResponse(500), FakeResponse(200, {"login": "ok"})]
    )

    def fake_get(*a, **k):
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(main.requests, "get", fake_get)
    assert main.fetch_profile("ok")["login"] == "ok"


def test_401_fails_fast(monkeypatch):
    calls = []

    def fake_get(*a, **k):
        calls.append(1)
        return FakeResponse(401)

    monkeypatch.setattr(main.requests, "get", fake_get)
    with pytest.raises(main.FetchError):
        main.fetch_profile("octocat")
    assert len(calls) == 1


def test_summary_row_handles_missing_name():
    row = main.summary_row({"login": "x", "name": None, "public_repos": 2, "followers": 5})
    assert row == {"login": "x", "name": "", "public_repos": 2, "followers": 5}


def test_unique_usernames_keeps_order():
    assert main.unique_usernames(["a", "B", "A", "b", " c "]) == ["a", "B", "c"]


def test_main_multiple_users_writes_files_and_csv(monkeypatch, tmp_path):
    def fake_get(url, **k):
        if url.endswith("/ghost"):
            return FakeResponse(404)
        login = url.rsplit("/", 1)[1]
        return FakeResponse(
            200, {"login": login, "name": login.title(), "public_repos": 3, "followers": 9}
        )

    monkeypatch.setattr(main.requests, "get", fake_get)
    out = tmp_path / "out"
    code = main.main(["octocat", "ghost", "torvalds", "--output", str(out)])

    assert code == 1  # one user failed
    assert json.loads((out / "octocat.json").read_text())["login"] == "octocat"
    assert not (out / "ghost.json").exists()

    with open(out / "summary.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["login"] for r in rows] == ["octocat", "torvalds"]
    assert list(rows[0].keys()) == ["login", "name", "public_repos", "followers"]

    assert "ghost" in (out / "errors.log").read_text()
