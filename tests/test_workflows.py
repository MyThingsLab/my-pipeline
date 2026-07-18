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
    # The bundled example — illustrative only, matches no real producer's
    # current ledger shape yet (see the module docstring/comment).
    steps = default_workflows()
    assert len(steps) >= 1
