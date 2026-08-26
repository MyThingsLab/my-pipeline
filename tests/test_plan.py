from __future__ import annotations

from mypipeline.plan import build_plan, build_waves
from mypipeline.workflows import default_workflows, parse

_FAN_OUT_JSON = """[
  {"id": "root", "trigger": {"type": "always"},
   "action": {"type": "run-cli", "stage": "sa"}, "engine": "none"},
  {"id": "left", "trigger": {"type": "after", "nodes": ["root"]},
   "action": {"type": "run-cli", "stage": "sb"}, "engine": "none"},
  {"id": "right", "trigger": {"type": "after", "nodes": ["root"]},
   "action": {"type": "run-cli", "stage": "sc"}, "engine": "none"},
  {"id": "join", "trigger": {"type": "after", "nodes": ["left", "right"]},
   "action": {"type": "run-cli", "stage": "sd"}, "engine": "none"}
]"""

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


def test_build_waves_groups_independent_nodes_sharing_a_prerequisite() -> None:
    waves = build_waves(parse(_FAN_OUT_JSON))
    assert [[i.stage for i in wave] for wave in waves] == [["sa"], ["sb", "sc"], ["sd"]]


def test_build_waves_flattened_matches_build_plan() -> None:
    flattened = [item for wave in build_waves(default_workflows()) for item in wave]
    assert flattened == build_plan(default_workflows())


def test_default_plan_fans_out_researcher_tester_changelogger() -> None:
    # The three no longer chain off each other -- none reads the others'
    # output, they only share fleet-dispatch as a prerequisite.
    waves = build_waves(default_workflows())
    fan_out_wave = next(w for w in waves if any(i.stage == "mytester" for i in w))
    assert {i.stage for i in fan_out_wave} == {"myresearcher", "mytester", "mychangelogger"}
