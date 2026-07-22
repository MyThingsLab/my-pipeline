# my-pipeline — agent instructions

You are developing **my-pipeline**, a MyThingsLab My[X] tool.

**Inherited rules:** obey [`./HARNESS.md`](./HARNESS.md) in full — the vendored
MyThingsLab build-harness rules. Do not restate or override them. Anything not
covered here defers to `HARNESS.md`, then `my-things-core/docs/CONVENTIONS.md`.

## This tool

- **Purpose:** owns the fleet's tool-chaining graph as data — one
  `workflows.json` of `Node`s, each with a `trigger` (`ledger` handoff |
  `after` join | `always` sweep) and an `action` (`file-issue` deferred |
  `run-cli` immediate). `mypipeline sync` fires the ledger→issue handoffs (as
  before); `mypipeline plan` emits the topo-ordered `run-cli` stages the driver
  (`my-fleet`) ticks, replacing its hand-coded cycle order. This makes each
  step's Engine cost a visible graph property, not scattered convention (see
  `my-things-core/docs/tools/my-pipeline.md`).
- **The single Engine call:** none — deterministic. Both firing a handoff
  (template substitution over a producer's `LedgerEntry.data`) and emitting the
  cycle plan (a topo-sort over `after` edges) need no judgment.
- **Invariants / rules:** never imports another tool's package and never
  runs another tool's code — this repo only *declares and orders* stages and
  *files* labeled issues; `my-fleet` binds `run-cli` stages to real argv and
  executes them. Every issue is filed through `Policy`. Never opens a PR, never
  merges, never uses a `Workspace` (no git checkout at all). A node with a
  missing required field is skipped, never guessed; a cycle in the graph is a
  hard error, never reordered around. Anything touching code stays a
  `file-issue` (deferred, `Policy`-gated, human-merged) node — `run-cli` is only
  for provably deterministic in-cycle steps. Dedupe against an already-open
  issue with the same title before filing.
- **Backlog label:** my-pipeline

## Testing

Fakes come from `mythings.testing` (opt-in via `pytest_plugins` in
`tests/conftest.py`; see `my-things-core/docs/CONVENTIONS.md`, "Shared test
fixtures"). Never copy fixture code into a conftest — only domain-specific
helpers live there.
