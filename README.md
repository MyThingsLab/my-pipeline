# my-pipeline

[![CI](https://github.com/MyThingsLab/my-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/MyThingsLab/my-pipeline/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/MyThingsLab/my-pipeline/branch/main/graph/badge.svg)](https://codecov.io/gh/MyThingsLab/my-pipeline) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A [MyThingsLab](../my-things-core) `My[X]` tool that declares the fleet's
**tool-to-tool handoffs** as data and drives them automatically, instead of
every producer tool hand-coding its own. Full design plan:
[`my-things-core/docs/tools/my-pipeline.md`](../my-things-core/docs/tools/my-pipeline.md).

Today a tool that wants to hand work to another tool files a labeled issue by
hand (e.g. `my-archivist` filing a `my-bibliography`-labeled issue per new
ISBN) — correct, but bespoke: the dependency lives only in that one
function's code, nowhere declared. MyPipeline reads a small declarative
**workflow DAG** off the shared runtime `Ledger` across every locally-checked-out
repo and files the handoff issue itself, deterministically. It never runs
another tool's code and never imports another tool's package — a handoff is
still a labeled issue, exactly like today, just declared once instead of
duplicated per producer.

Sits on a third axis alongside **MyOrchestrator** (picks what to build next)
and **MyConductor** (orders already-open PRs into a merge sequence): what
happens automatically once a step finishes.

## The single Engine call

None in v0 — fully deterministic. Filling a workflow step's issue title/body
from the producer's own `LedgerEntry.data` is plain template substitution, no
judgment required. An optional Engine seam for arbitrating multiple workflow
steps matching the same event is described in the design doc but not built —
no real multi-match case exists yet.

## Run

```bash
mypipeline sync --repo-root .. --org MyThingsLab --workflows workflows.json
```

Scans every repo under `--repo-root` with a `.mythings/ledger.jsonl`, finds
ledger entries newer than MyPipeline's own last-recorded bookmark for that
repo, matches them against the declared workflow steps, and files a labeled
issue in each step's target repo — deduped against an already-open issue with
the same title.

## Workflow steps

Each step in `workflows.json` (`src/mypipeline/workflows.json`, the bundled
default) declares:

```json
{
  "id": "idea-verdict-build-to-new-tool-tracking",
  "on": { "tool": "myidea", "kind": "idea_explored", "outcome": "success" },
  "require_fields": ["idea_issue"],
  "require_data": { "verdict": "build" },
  "then": {
    "repo": "my-things-core",
    "label": "new-tool",
    "title": "new tool: draft design doc for MyThingsLab/my-idea#{idea_issue}",
    "body": "..."
  }
}
```

- `on` — the ledger entry `(tool, kind, outcome)` this step watches for.
- `require_fields` — entry `data` keys that must be present (and non-empty) for
  the template to fill; missing one skips the step rather than guessing.
- `require_data` — optional exact-value filters on entry `data` (e.g. only
  fire when `verdict == "build"`, not `fold`/`park`/absent). A step with no
  `require_data` fires on every entry matching `on`.
- `then` — the target repo/label and `str.format`-style title/body templates,
  filled from the entry's own `data`.

Two steps ship today: `example-catalog-to-bibliography` (illustrative only —
`my-archivist`'s real `catalog` ledger entry is a batch summary, not one entry
per ISBN, so this doesn't fire against a real run yet; see the design doc's
"Dependencies & build order") and `idea-verdict-build-to-new-tool-tracking`
(real and wired: fulfills the "open a new-tool tracking issue" half of
`my-idea#2`'s own proposal — drafting the actual design-doc *content* stays
`my-idea#2`'s job, not MyPipeline's, since MyPipeline never runs another
tool's code or opens a PR).

## Install (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../my-things-core -e ".[dev]"
pytest
```

## License

MIT — see [`LICENSE`](LICENSE).
