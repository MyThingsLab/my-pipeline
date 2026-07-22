from __future__ import annotations

from mypipeline.plan import build_plan
from mypipeline.workflows import default_workflows, parse

_MIXED_JSON = """[
  {"id": "handoff", "on": {"tool": "t", "kind": "k", "outcome": "success"},
   "then": {"repo": "r", "label": "l", "title": "x", "body": "y"}},
  {"id": "second", "trigger": {"type": "after", "nodes": ["first"]},
   "action": {"type": "run-cli", "stage": "sb"}, "engine": "optional"},
  {"id": "first", "trigger": {"type": "always"},
   "action": {"type": "run-cli", "stage": "sa"}, "engine": "required"}
]"""


def test_build_plan_emits_only_run_cli_nodes_topo_ordered() -> None:
    items = build_plan(parse(_MIXED_JSON))
    # The file-issue "handoff" node is not a cycle stage -- it's fired by sync.
    assert [i.node_id for i in items] == ["first", "second"]
    assert [i.stage for i in items] == ["sa", "sb"]
    assert [i.engine for i in items] == ["required", "optional"]


def test_default_plan_matches_todays_cycle_order() -> None:
    # The graph must reproduce the 10-step order fleet_cycle ran by hand, with
    # mypipeline's own handoff sync wired in before the final notify.
    stages = [i.stage for i in build_plan(default_workflows())]
    assert stages == [
        "myplanner",
        "fleet-dispatch",
        "myresearcher",
        "mytester",
        "mychangelogger",
        "mydocs",
        "mydashboard",
        "myprojector",
        "myreporter",
        "mypipeline-sync",
        "mytelegrambot",
    ]
