from __future__ import annotations

from mythings.ledger import LedgerEntry

from mypipeline.workflows import (
    default_workflows,
    fill,
    matches,
    missing_fields,
    parse,
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


def test_parse_builds_a_workflow_step() -> None:
    steps = parse(_JSON)
    assert len(steps) == 1
    step = steps[0]
    assert step.id == "catalog-to-bibliography"
    assert step.on_tool == "myarchivist"
    assert step.require_fields == ("isbn",)
    assert step.target_repo == "my-bibliography"


def test_matches_checks_tool_kind_and_outcome() -> None:
    step = parse(_JSON)[0]
    assert matches(step, _entry(isbn="123"))
    assert not matches(step, LedgerEntry(tool="other", kind="catalog", outcome="success"))
    assert not matches(step, LedgerEntry(tool="myarchivist", kind="catalog", outcome="failure"))


def test_missing_fields_reports_unmet_requirements() -> None:
    step = parse(_JSON)[0]
    assert missing_fields(step, _entry(isbn="123")) == []
    assert missing_fields(step, _entry()) == ["isbn"]
    assert missing_fields(step, _entry(isbn="")) == ["isbn"]  # empty counts as missing


def test_fill_substitutes_entry_data() -> None:
    step = parse(_JSON)[0]
    entry = _entry(isbn="9780131103627", title="The C Programming Language", author="K&R")
    assert fill(step.title_template, entry) == "bibliography: catalog isbn:9780131103627"
    assert "K&R" in fill(step.body_template, entry)


def test_default_workflows_load_without_error() -> None:
    steps = default_workflows()
    ids = {s.id for s in steps}
    # The archivist->bibliography example is illustrative only (matches no
    # shipped producer's current ledger shape yet); the myidea step is real.
    assert "example-catalog-to-bibliography" in ids
    assert "idea-verdict-build-to-new-tool-tracking" in ids


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
    step = parse(_REQUIRE_DATA_JSON)[0]
    assert step.require_data == (("verdict", "build"),)


def test_matches_respects_require_data_value() -> None:
    step = parse(_REQUIRE_DATA_JSON)[0]
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
    assert matches(step, build)
    assert not matches(step, fold)
    assert not matches(step, deterministic_only)  # verdict is None -- never "build"


def test_step_with_no_require_data_matches_regardless_of_data() -> None:
    step = parse(_JSON)[0]  # the archivist example has no require_data at all
    assert step.require_data == ()
    assert matches(step, _entry(isbn="123", anything="else"))
