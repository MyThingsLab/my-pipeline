from __future__ import annotations

import argparse
from pathlib import Path

from mypipeline.sync import RepoSync, Sync
from mypipeline.workflows import parse


def _render(results: list[RepoSync]) -> str:
    if not results:
        return "nothing new to sync"
    lines = []
    for r in results:
        filed = [h for h in r.handoffs if h.outcome == "success"]
        lines.append(f"{r.repo}: {len(filed)} filed, {len(r.handoffs)} evaluated")
        for h in r.handoffs:
            suffix = f" -> {h.target_repo}#{h.issue}" if h.issue is not None else f" ({h.detail})"
            lines.append(f"  {h.workflow_id}: {h.outcome}{suffix}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mypipeline",
        description="File declared cross-tool handoffs as labeled issues.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sync = sub.add_parser("sync", help="scan every repo's ledger and file new handoffs")
    sync.add_argument("--repo-root", type=Path, required=True, help="workspace root")
    sync.add_argument("--org", required=True, help="GitHub org, e.g. MyThingsLab")
    sync.add_argument("--repos", nargs="*", help="repos to scan (default: every subdirectory)")
    sync.add_argument("--workflows", type=Path, help="workflow DAG JSON (default: bundled example)")

    args = parser.parse_args(argv)
    repos = args.repos
    if repos is None:
        repos = sorted(p.name for p in args.repo_root.iterdir() if p.is_dir())
    workflows = parse(args.workflows.read_text(encoding="utf-8")) if args.workflows else None

    results = Sync(repo_root=args.repo_root, org=args.org, repos=repos, workflows=workflows).run()
    print(_render(results))
    if any(h.outcome == "failure" for r in results for h in r.handoffs):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
