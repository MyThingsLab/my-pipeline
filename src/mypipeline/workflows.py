from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files

from mythings.ledger import LedgerEntry


@dataclass(frozen=True)
class WorkflowStep:
    id: str
    on_tool: str
    on_kind: str
    on_outcome: str
    require_fields: tuple[str, ...]
    target_repo: str
    label: str
    title_template: str
    body_template: str
    # (field, exact value) pairs, e.g. verdict == "build" -- empty means "no
    # data-value filter, only tool/kind/outcome must match".
    require_data: tuple[tuple[str, str], ...] = ()


def parse(text: str) -> list[WorkflowStep]:
    steps = []
    for obj in json.loads(text):
        on = obj["on"]
        then = obj["then"]
        steps.append(
            WorkflowStep(
                id=obj["id"],
                on_tool=on["tool"],
                on_kind=on["kind"],
                on_outcome=on["outcome"],
                require_fields=tuple(obj.get("require_fields", [])),
                require_data=tuple(obj.get("require_data", {}).items()),
                target_repo=then["repo"],
                label=then["label"],
                title_template=then["title"],
                body_template=then["body"],
            )
        )
    return steps


def default_workflows() -> list[WorkflowStep]:
    return parse(files("mypipeline").joinpath("workflows.json").read_text(encoding="utf-8"))


def matches(step: WorkflowStep, entry: LedgerEntry) -> bool:
    return (
        entry.tool == step.on_tool
        and entry.kind == step.on_kind
        and entry.outcome == step.on_outcome
        and all(entry.data.get(field) == value for field, value in step.require_data)
    )


def missing_fields(step: WorkflowStep, entry: LedgerEntry) -> list[str]:
    return [field for field in step.require_fields if not entry.data.get(field)]


def fill(template: str, entry: LedgerEntry) -> str:
    return template.format(**entry.data)
