from __future__ import annotations

import pytest
from mythings.ledger import LedgerEntry

from mypipeline.workflows import (
    Action,
    Node,
    Trigger,
    default_workflows,
    fill,
    matches,
    missing_fields,
    parse,
    topo_sort,
)

_JSON = """[
  {
    "id": "catalog-to-bibliography",
    "on": {"tool": "myarchivist", "kind": "catalog", "outcome": "success"},
    "require_fields": ["isbn"],
    "then": {
      "repo": "my-bibliography",
      "label": "my-bibliography",
      "title": "bibliography: catalog isbn:{isbn}",
      "body": "isbn:{isbn}\\n\\nCataloged from `{title}` by {author}."
    }
  }
]"""


def _entry(**data) -> LedgerEntry:
    return LedgerEntry(tool="myarchivist", kind="catalog", outcome="success", data=data)


def test_parse_lowers_legacy_on_then_into_a_ledger_file_issue_node() -> None:
    nodes = parse(_JSON)
    assert len(nodes) == 1
    node = nodes[0]
    assert node.id == "catalog-to-bibliography"
    assert node.trigger.type == "ledger"
    assert node.trigger.tool == "myarchivist"
    assert node.require_fields == ("isbn",)
    assert node.action.type == "file-issue"
    assert node.action.repo == "my-bibliography"


def test_matches_checks_tool_kind_and_outcome() -> None:
    node = parse(_JSON)[0]
    assert matches(node, _entry(isbn="123"))
    assert not matches(node, LedgerEntry(tool="other", kind="catalog", outcome="success"))
    assert not matches(node, LedgerEntry(tool="myarchivist", kind="catalog", outcome="failure"))


def test_missing_fields_reports_unmet_requirements() -> None:
    node = parse(_JSON)[0]
    assert missing_fields(node, _entry(isbn="123")) == []
    assert missing_fields(node, _entry()) == ["isbn"]
    assert missing_fields(node, _entry(isbn="")) == ["isbn"]  # empty counts as missing


def test_fill_substitutes_entry_data() -> None:
    node = parse(_JSON)[0]
    entry = _entry(isbn="9780131103627", title="The C Programming Language", author="K&R")
    assert fill(node.action.title, entry) == "bibliography: catalog isbn:9780131103627"
    assert "K&R" in fill(node.action.body, entry)


def test_default_workflows_load_without_error() -> None:
    nodes = default_workflows()
    ids = {n.id for n in nodes}
    # The archivist->bibliography example is illustrative only (matches no
    # shipped producer's current ledger shape yet); the myidea step is real.
    assert "example-catalog-to-bibliography" in ids
    assert "idea-verdict-build-to-new-tool-tracking" in ids
    # The cycle stages live in the same graph now.
    assert {"planner", "dispatch", "handoffs", "telegram"} <= ids


_REQUIRE_DATA_JSON = """[
  {
    "id": "idea-verdict-build",
    "on": {"tool": "myidea", "kind": "idea_explored", "outcome": "success"},
    "require_fields": ["idea_issue"],
    "require_data": {"verdict": "build"},
    "then": {
      "repo": "my-things-core",
      "label": "new-tool",
      "title": "new tool: draft design doc for MyThingsLab/my-idea#{idea_issue}",
      "body": "verdict=build on my-idea#{idea_issue}"
    }
  }
]"""


def test_parse_reads_require_data() -> None:
    node = parse(_REQUIRE_DATA_JSON)[0]
    assert node.trigger.require_data == (("verdict", "build"),)


def test_matches_respects_require_data_value() -> None:
    node = parse(_REQUIRE_DATA_JSON)[0]
    build = LedgerEntry(
        tool="myidea",
        kind="idea_explored",
        outcome="success",
        data={"verdict": "build", "idea_issue": 1},
    )
    fold = LedgerEntry(
        tool="myidea",
        kind="idea_explored",
        outcome="success",
        data={"verdict": "fold", "idea_issue": 1},
    )
    deterministic_only = LedgerEntry(
        tool="myidea", kind="idea_explored", outcome="success", data={"idea_issue": 1}
    )
    assert matches(node, build)
    assert not matches(node, fold)
    assert not matches(node, deterministic_only)  # verdict is None -- never "build"


def test_node_with_no_require_data_matches_regardless_of_data() -> None:
    node = parse(_JSON)[0]  # the archivist example has no require_data at all
    assert node.trigger.require_data == ()
    assert matches(node, _entry(isbn="123", anything="else"))


# --- the new graph layer: triggers, actions, topo-sort ---

_GRAPH_JSON = """[
  {"id": "a", "trigger": {"type": "always"},
   "action": {"type": "run-cli", "stage": "sa"}, "engine": "required"},
  {"id": "b", "trigger": {"type": "after", "nodes": ["a"]},
   "action": {"type": "run-cli", "stage": "sb"}},
  {"id": "c", "trigger": {"type": "after", "nodes": ["b"]},
   "action": {"type": "run-cli", "stage": "sc"}}
]"""


def test_parse_reads_new_trigger_and_action_schema() -> None:
    nodes = parse(_GRAPH_JSON)
    a, b, c = nodes
    assert a.trigger.type == "always"
    assert a.action.type == "run-cli" and a.action.stage == "sa"
    assert a.engine == "required"
    assert b.engine == "none"  # defaulted
    assert b.trigger.after == ("a",)
    assert c.trigger.after == ("b",)


def test_run_cli_node_never_matches_a_ledger_entry() -> None:
    node = parse(_GRAPH_JSON)[0]
    assert not matches(node, LedgerEntry(tool="sa", kind="always", outcome="success"))


def test_topo_sort_orders_dependencies_before_dependents() -> None:
    # Declared c, b, a out of order -- topo-sort must still yield a, b, c.
    nodes = parse(_GRAPH_JSON)
    shuffled = [nodes[2], nodes[0], nodes[1]]
    assert [n.id for n in topo_sort(shuffled)] == ["a", "b", "c"]


def test_topo_sort_breaks_ties_by_declaration_order() -> None:
    n1 = Node("x", Trigger("always"), Action("run-cli", stage="s"))
    n2 = Node("y", Trigger("always"), Action("run-cli", stage="s"))
    assert [n.id for n in topo_sort([n1, n2])] == ["x", "y"]
    assert [n.id for n in topo_sort([n2, n1])] == ["y", "x"]


def test_topo_sort_raises_on_a_cycle() -> None:
    a = Node("a", Trigger("after", after=("b",)), Action("run-cli", stage="s"))
    b = Node("b", Trigger("after", after=("a",)), Action("run-cli", stage="s"))
    with pytest.raises(ValueError, match="cycle"):
        topo_sort([a, b])


def test_topo_sort_ignores_after_refs_outside_the_subset() -> None:
    # A run-cli node depending on a node not in the given list still sorts.
    n = Node("only", Trigger("after", after=("missing",)), Action("run-cli", stage="s"))
    assert [x.id for x in topo_sort([n])] == ["only"]
