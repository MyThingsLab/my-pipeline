from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from myguard import Guard
from mythings.github import GitHub, GitHubError, Runner, _gh
from mythings.isolation import in_github_actions
from mythings.ledger import Ledger, LedgerEntry
from mythings.policy import Action, Decision, Policy

from mypipeline.workflows import Node, default_workflows, fill, matches, missing_fields

TOOL = "mypipeline"


@dataclass(frozen=True)
class Handoff:
    workflow_id: str
    target_repo: str
    outcome: str  # success | skipped | duplicate | failure
    issue: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class RepoSync:
    repo: str
    handoffs: tuple[Handoff, ...] = field(default_factory=tuple)


def _ledger_path(repo_root: Path, repo: str) -> Path:
    return repo_root / repo / ".mythings" / "ledger.jsonl"


def _last_scan_ts(entries: list[LedgerEntry]) -> str | None:
    own = [e for e in entries if e.tool == TOOL and e.kind == "handoff"]
    return max((e.ts for e in own), default=None)


def _open_titles(github: GitHub, label: str) -> set[str]:
    try:
        issues = github.list_issues(labels=[label], state="open", limit=100)
    except GitHubError:
        return set()
    return {i.title for i in issues}


def _ensure_label(runner: Runner, repo: str | None, label: str) -> None:
    argv = ["label", "create", label, "--force"]
    if repo:
        argv += ["--repo", repo]
    runner(argv)


class Sync:
    def __init__(
        self,
        *,
        repo_root: str | Path,
        org: str,
        repos: list[str],
        policy: Policy | None = None,
        runner: Runner = _gh,
        workflows: list[Node] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.org = org
        self.repos = repos
        self.policy: Policy = policy or Guard()
        self.runner = runner
        nodes = workflows if workflows is not None else default_workflows()
        # Sync only files issues -- run-cli / non-ledger nodes are the driver's
        # to tick (see mypipeline.plan), never fired here.
        self.workflows = [
            n for n in nodes if n.trigger.type == "ledger" and n.action.type == "file-issue"
        ]

    def run(self) -> list[RepoSync]:
        return [r for repo in self.repos if (r := self._sync_repo(repo)) is not None]

    def _sync_repo(self, repo: str) -> RepoSync | None:
        path = _ledger_path(self.repo_root, repo)
        if not path.exists():
            return None
        ledger = Ledger(path)
        entries = list(ledger)
        bookmark = _last_scan_ts(entries)
        new_entries = [e for e in entries if bookmark is None or e.ts > bookmark]
        if not new_entries:
            return None

        handoffs: list[Handoff] = []
        for entry in new_entries:
            for node in self.workflows:
                if matches(node, entry):
                    handoffs.append(self._evaluate(node, entry))

        filed = [h for h in handoffs if h.outcome == "success"]
        ledger.record(
            tool=TOOL,
            kind="handoff",
            outcome="success" if filed else "clean",
            detail=f"scanned {len(new_entries)}, filed {len(filed)}",
            repo=repo,
            handoffs=[
                {"workflow_id": h.workflow_id, "target_repo": h.target_repo, "issue": h.issue}
                for h in handoffs
            ],
        )
        return RepoSync(repo=repo, handoffs=tuple(handoffs))

    def _evaluate(self, node: Node, entry: LedgerEntry) -> Handoff:
        repo, label = node.action.repo, node.action.label
        missing = missing_fields(node, entry)
        if missing:
            return Handoff(node.id, repo, "skipped", detail=f"missing field: {missing[0]}")

        try:
            title = fill(node.action.title, entry)
            body = fill(node.action.body, entry)
        except KeyError as exc:
            return Handoff(node.id, repo, "skipped", detail=f"missing field: {exc}")

        github = GitHub(f"{self.org}/{repo}", runner=self.runner)
        try:
            if title in _open_titles(github, label):
                return Handoff(node.id, repo, "duplicate", detail=title)

            action = Action(kind="issue-create", payload={"title": title, "label": label})
            gate = self.policy.evaluate(action).under(unattended=in_github_actions())
            if gate is not Decision.ALLOW:
                return Handoff(node.id, repo, "skipped", detail="policy denied")

            created = github.create_issue(title=title, body=body)
            try:
                github.add_labels(created.number, [label])
            except GitHubError:
                # First handoff filed against a fresh target repo: the label
                # doesn't exist yet. Create it (idempotent via --force) and retry.
                _ensure_label(self.runner, github.repo, label)
                github.add_labels(created.number, [label])
            return Handoff(node.id, repo, "success", issue=created.number, detail=title)
        except GitHubError as exc:
            return Handoff(node.id, repo, "failure", detail=str(exc))
