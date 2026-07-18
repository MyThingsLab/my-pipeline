from __future__ import annotations

import json
from pathlib import Path

from mythings.github import GitHubError
from mythings.ledger import Ledger
from mythings.policy import ALLOW, Action, Decision, PolicyResult
from mythings.testing import FakeGh

from mypipeline.sync import Sync
from mypipeline.workflows import WorkflowStep

_STEP = WorkflowStep(
    id="catalog-to-bibliography",
    on_tool="myarchivist",
    on_kind="catalog",
    on_outcome="success",
    require_fields=("isbn",),
    target_repo="my-bibliography",
    label="my-bibliography",
    title_template="bibliography: catalog isbn:{isbn}",
    body_template="isbn:{isbn}\n\nCataloged from `{title}` by {author}.",
)


class _AllowPolicy:
    def evaluate(self, action: Action) -> PolicyResult:
        return ALLOW


def _seed_ledger(root: Path, repo: str) -> Ledger:
    path = root / repo / ".mythings" / "ledger.jsonl"
    return Ledger(path)


def _fake(*, open_issues: list[dict] | None = None) -> FakeGh:
    return FakeGh(
        {
            ("issue", "list"): json.dumps(open_issues or []),
            ("issue", "create"): "https://github.com/o/my-bibliography/issues/9\n",
            ("issue", "edit"): "",
        }
    )


def test_matching_entry_files_a_handoff_issue(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(
        tool="myarchivist",
        kind="catalog",
        outcome="success",
        isbn="9780131103627",
        title="The C Programming Language",
        author="K&R",
    )
    fake = _fake()

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert len(results) == 1
    handoffs = results[0].handoffs
    assert len(handoffs) == 1
    assert handoffs[0].outcome == "success"
    assert handoffs[0].issue == 9
    create_call = next(c for c in fake.calls if c[:2] == ["issue", "create"])
    title = create_call[create_call.index("--title") + 1]
    assert title == "bibliography: catalog isbn:9780131103627"

    entries = list(ledger)
    assert entries[-1].kind == "handoff"
    assert entries[-1].outcome == "success"


def test_missing_required_field_is_skipped_not_filed(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(tool="myarchivist", kind="catalog", outcome="success", title="x", author="y")
    fake = _fake()

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert results[0].handoffs[0].outcome == "skipped"
    assert not any(c[:2] == ["issue", "create"] for c in fake.calls)


def test_template_field_missing_beyond_required_is_skipped(tmp_path: Path) -> None:
    # `isbn` (the only required field) is present, but the body template also
    # references `author`, which this entry doesn't carry -- must not guess.
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(tool="myarchivist", kind="catalog", outcome="success", isbn="1", title="x")
    fake = _fake()

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert results[0].handoffs[0].outcome == "skipped"
    assert not any(c[:2] == ["issue", "create"] for c in fake.calls)


def test_already_open_issue_is_not_refiled(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(
        tool="myarchivist", kind="catalog", outcome="success", isbn="1", title="x", author="y"
    )
    fake = _fake(
        open_issues=[
            {
                "number": 3,
                "title": "bibliography: catalog isbn:1",
                "body": "",
                "labels": [],
                "url": "https://x/3",
            }
        ]
    )

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert results[0].handoffs[0].outcome == "duplicate"
    assert not any(c[:2] == ["issue", "create"] for c in fake.calls)


class _DenyPolicy:
    def evaluate(self, action: Action) -> PolicyResult:
        return PolicyResult(Decision.DENY)


def test_policy_deny_skips_without_filing(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(
        tool="myarchivist", kind="catalog", outcome="success", isbn="1", title="x", author="y"
    )
    fake = _fake()

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_DenyPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert results[0].handoffs[0].outcome == "skipped"
    assert not any(c[:2] == ["issue", "create"] for c in fake.calls)


def test_no_new_entries_since_bookmark_is_a_noop(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(
        tool="myarchivist", kind="catalog", outcome="success", isbn="1", title="x", author="y"
    )
    fake = _fake()
    sync = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    )

    first = sync.run()
    assert len(first[0].handoffs) == 1

    second = sync.run()  # nothing new since the bookmark advanced
    assert second == []


def test_no_ledger_at_all_is_skipped_silently(tmp_path: Path) -> None:
    (tmp_path / "empty-repo").mkdir()
    results = Sync(
        repo_root=tmp_path, org="o", repos=["empty-repo"], policy=_AllowPolicy(), workflows=[_STEP]
    ).run()
    assert results == []


def test_unrelated_entry_matches_no_step(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-tester")
    ledger.record(tool="mytester", kind="run", outcome="success", target="pkg:f")
    fake = _fake()

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-tester"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert results[0].handoffs == ()  # entry scanned, but matched no workflow step
    assert fake.calls == []


def test_label_missing_on_target_repo_is_created_lazily(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(
        tool="myarchivist", kind="catalog", outcome="success", isbn="1", title="x", author="y"
    )
    edit_calls = {"n": 0}

    def _edit(argv: list[str]) -> str:
        edit_calls["n"] += 1
        if edit_calls["n"] == 1:
            raise GitHubError("label not found")
        return ""

    fake = FakeGh(
        {
            ("issue", "list"): "[]",
            ("issue", "create"): "https://github.com/o/my-bibliography/issues/9\n",
            ("issue", "edit"): _edit,
            ("label", "create"): "",
        }
    )

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert results[0].handoffs[0].outcome == "success"
    assert any(c[:2] == ["label", "create"] for c in fake.calls)


def test_list_issues_error_is_treated_as_no_open_issues(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(
        tool="myarchivist", kind="catalog", outcome="success", isbn="1", title="x", author="y"
    )

    def _list(argv: list[str]) -> str:
        raise GitHubError("repo not found")

    fake = FakeGh(
        {
            ("issue", "list"): _list,
            ("issue", "create"): "https://github.com/o/my-bibliography/issues/9\n",
            ("issue", "edit"): "",
        }
    )

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert results[0].handoffs[0].outcome == "success"  # fails open, still tries to file


def test_create_issue_error_is_recorded_as_failure(tmp_path: Path) -> None:
    ledger = _seed_ledger(tmp_path, "my-archivist")
    ledger.record(
        tool="myarchivist", kind="catalog", outcome="success", isbn="1", title="x", author="y"
    )

    def _create(argv: list[str]) -> str:
        raise GitHubError("repo does not exist")

    fake = FakeGh({("issue", "list"): "[]", ("issue", "create"): _create})

    results = Sync(
        repo_root=tmp_path,
        org="o",
        repos=["my-archivist"],
        policy=_AllowPolicy(),
        runner=fake,
        workflows=[_STEP],
    ).run()

    assert results[0].handoffs[0].outcome == "failure"
