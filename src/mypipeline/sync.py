from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from myguard import Guard
from mythings.github import GitHub, GitHubError, Runner, _gh
from mythings.isolation import in_github_actions
from mythings.ledger import Ledger, LedgerEntry
from mythings.policy import Action, Decision, Policy

from mypipeline.workflows import WorkflowStep, default_workflows, fill, matches, missing_fields

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
        workflows: list[WorkflowStep] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.org = org
        self.repos = repos
        self.policy: Policy = policy or Guard()
        self.runner = runner
        self.workflows = workflows if workflows is not None else default_workflows()

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
            for step in self.workflows:
                if matches(step, entry):
                    handoffs.append(self._evaluate(step, entry))

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

    def _evaluate(self, step: WorkflowStep, entry: LedgerEntry) -> Handoff:
        missing = missing_fields(step, entry)
        if missing:
            return Handoff(
                step.id, step.target_repo, "skipped", detail=f"missing field: {missing[0]}"
            )

        try:
            title = fill(step.title_template, entry)
            body = fill(step.body_template, entry)
        except KeyError as exc:
            return Handoff(step.id, step.target_repo, "skipped", detail=f"missing field: {exc}")

        github = GitHub(f"{self.org}/{step.target_repo}", runner=self.runner)
        try:
            if title in _open_titles(github, step.label):
                return Handoff(step.id, step.target_repo, "duplicate", detail=title)

            action = Action(kind="issue-create", payload={"title": title, "label": step.label})
            gate = self.policy.evaluate(action).under(unattended=in_github_actions())
            if gate is not Decision.ALLOW:
                return Handoff(step.id, step.target_repo, "skipped", detail="policy denied")

            created = github.create_issue(title=title, body=body)
            try:
                github.add_labels(created.number, [step.label])
            except GitHubError:
                # First handoff filed against a fresh target repo: the label
                # doesn't exist yet. Create it (idempotent via --force) and retry.
                _ensure_label(self.runner, github.repo, step.label)
                github.add_labels(created.number, [step.label])
            return Handoff(step.id, step.target_repo, "success", issue=created.number, detail=title)
        except GitHubError as exc:
            return Handoff(step.id, step.target_repo, "failure", detail=str(exc))
