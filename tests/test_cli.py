from __future__ import annotations

from pathlib import Path

import pytest

from mypipeline import cli
from mypipeline.sync import Handoff, RepoSync


def test_render_reports_nothing_new() -> None:
    assert cli._render([]) == "nothing new to sync"


def test_render_summarizes_each_repo_and_handoff() -> None:
    results = [
        RepoSync(
            repo="my-archivist",
            handoffs=(
                Handoff("wf1", "my-bibliography", "success", issue=9),
                Handoff("wf2", "my-bibliography", "skipped", detail="missing field: isbn"),
            ),
        )
    ]
    out = cli._render(results)
    assert "my-archivist: 1 filed, 2 evaluated" in out
    assert "wf1: success -> my-bibliography#9" in out
    assert "wf2: skipped (missing field: isbn)" in out


def _stub_sync(monkeypatch: pytest.MonkeyPatch, results: list[RepoSync]) -> dict:
    captured: dict = {}

    class _Stub:
        def __init__(self, **kwargs: object) -> None:
            captured["kwargs"] = kwargs

        def run(self) -> list[RepoSync]:
            return results

    monkeypatch.setattr(cli, "Sync", _Stub)
    return captured


def test_sync_subcommand_defaults_repos_to_every_subdirectory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "repo-a").mkdir()
    (tmp_path / "repo-b").mkdir()
    (tmp_path / "not-a-repo.txt").write_text("x", encoding="utf-8")
    captured = _stub_sync(monkeypatch, [])

    assert cli.main(["sync", "--repo-root", str(tmp_path), "--org", "o"]) == 0

    assert captured["kwargs"]["repos"] == ["repo-a", "repo-b"]


def test_sync_subcommand_honors_explicit_repos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _stub_sync(monkeypatch, [])

    cli.main(["sync", "--repo-root", str(tmp_path), "--org", "o", "--repos", "my-x", "my-y"])

    assert captured["kwargs"]["repos"] == ["my-x", "my-y"]


def test_sync_subcommand_nonzero_on_any_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_sync(
        monkeypatch,
        [RepoSync(repo="r", handoffs=(Handoff("wf", "target", "failure", detail="boom"),))],
    )

    code = cli.main(["sync", "--repo-root", str(tmp_path), "--org", "o", "--repos", "r"])

    assert code == 1


def test_sync_subcommand_zero_when_no_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_sync(
        monkeypatch,
        [RepoSync(repo="r", handoffs=(Handoff("wf", "target", "success", issue=1),))],
    )

    code = cli.main(["sync", "--repo-root", str(tmp_path), "--org", "o", "--repos", "r"])

    assert code == 0


def test_missing_subcommand_is_a_usage_error() -> None:
    with pytest.raises(SystemExit):
        cli.main([])
