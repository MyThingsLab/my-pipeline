# my-pipeline — agent instructions

You are developing **my-pipeline**, a MyThingsLab My[X] tool.

**Inherited rules:** obey [`./HARNESS.md`](./HARNESS.md) in full — the vendored
MyThingsLab build-harness rules. Do not restate or override them. Anything not
covered here defers to `HARNESS.md`, then `my-things-core/docs/CONVENTIONS.md`.

## This tool

- **Purpose:** declares the fleet's tool-to-tool handoffs as a workflow DAG
  and files them as labeled issues, instead of every producer tool
  hand-coding its own (see `my-things-core/docs/tools/my-pipeline.md`).
- **The single Engine call:** none — deterministic (v0). Filling an issue
  title/body from a producer's own `LedgerEntry.data` is plain template
  substitution, no judgment needed.
- **Invariants / rules:** never imports another tool's package and never
  runs another tool's code — a handoff is always a labeled issue, filed
  through `Policy`. Never opens a PR, never merges, never uses a
  `Workspace` (no git checkout at all). A workflow step with a missing
  required field is skipped, never guessed. Dedupe against an already-open
  issue with the same title before filing.
- **Backlog label:** my-pipeline

## Testing

Fakes come from `mythings.testing` (opt-in via `pytest_plugins` in
`tests/conftest.py`; see `my-things-core/docs/CONVENTIONS.md`, "Shared test
fixtures"). Never copy fixture code into a conftest — only domain-specific
helpers live there.
