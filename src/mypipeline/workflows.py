from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files

from mythings.ledger import LedgerEntry


# A node fires either off a ledger entry (a cross-tool handoff), after other
# nodes complete (ordering / join), or every tick (a periodic sweep). Kept as
# one dataclass with a `type` discriminator rather than a class hierarchy so it
# round-trips JSON without isinstance dispatch at the parse boundary.
@dataclass(frozen=True)
class Trigger:
    type: str  # "ledger" | "after" | "always"
    # ledger:
    tool: str = ""
    kind: str = ""
    outcome: str = ""
    require_data: tuple[tuple[str, str], ...] = ()  # (field, exact value) pairs
    # after:
    after: tuple[str, ...] = ()


# A node either files a labeled issue (deferred: a worker closes it later, that's
# where the Engine call lives) or runs a tool CLI in-cycle (immediate). `stage`
# names a resolver the driver binds to concrete argv at tick time -- the graph
# owns *what runs and in what order*, not the runtime-bound arguments.
@dataclass(frozen=True)
class Action:
    type: str  # "file-issue" | "run-cli"
    # file-issue:
    repo: str = ""
    label: str = ""
    title: str = ""
    body: str = ""
    # run-cli:
    stage: str = ""


@dataclass(frozen=True)
class Node:
    id: str
    trigger: Trigger
    action: Action
    require_fields: tuple[str, ...] = ()
    engine: str = "none"  # declared cost: none | optional | required | deferred


def _parse_node(obj: dict) -> Node:
    # Legacy sugar: an {on, then} entry is a ledger-triggered file-issue node.
    if "on" in obj or "then" in obj:
        on = obj["on"]
        then = obj["then"]
        trigger = Trigger(
            type="ledger",
            tool=on["tool"],
            kind=on["kind"],
            outcome=on["outcome"],
            require_data=tuple(obj.get("require_data", {}).items()),
        )
        action = Action(
            type="file-issue",
            repo=then["repo"],
            label=then["label"],
            title=then["title"],
            body=then["body"],
        )
        return Node(
            id=obj["id"],
            trigger=trigger,
            action=action,
            require_fields=tuple(obj.get("require_fields", [])),
            engine=obj.get("engine", "none"),
        )

    t = obj["trigger"]
    a = obj["action"]
    trigger = Trigger(
        type=t["type"],
        tool=t.get("tool", ""),
        kind=t.get("kind", ""),
        outcome=t.get("outcome", ""),
        require_data=tuple(t.get("require_data", {}).items()),
        after=tuple(t.get("nodes", [])),
    )
    action = Action(
        type=a["type"],
        repo=a.get("repo", ""),
        label=a.get("label", ""),
        title=a.get("title", ""),
        body=a.get("body", ""),
        stage=a.get("stage", ""),
    )
    return Node(
        id=obj["id"],
        trigger=trigger,
        action=action,
        require_fields=tuple(obj.get("require_fields", [])),
        engine=obj.get("engine", "none"),
    )


def parse(text: str) -> list[Node]:
    return [_parse_node(obj) for obj in json.loads(text)]


def default_workflows() -> list[Node]:
    return parse(files("mypipeline").joinpath("workflows.json").read_text(encoding="utf-8"))


def matches(node: Node, entry: LedgerEntry) -> bool:
    t = node.trigger
    return (
        t.type == "ledger"
        and entry.tool == t.tool
        and entry.kind == t.kind
        and entry.outcome == t.outcome
        and all(entry.data.get(field) == value for field, value in t.require_data)
    )


def missing_fields(node: Node, entry: LedgerEntry) -> list[str]:
    return [field for field in node.require_fields if not entry.data.get(field)]


def fill(template: str, entry: LedgerEntry) -> str:
    return template.format(**entry.data)


def topo_sort(nodes: list[Node]) -> list[Node]:
    # Post-order DFS over `after` edges: dependencies land before dependents,
    # ties broken by declaration order (deterministic). `after` refs to nodes
    # outside `nodes` are ignored, so a subset (e.g. only run-cli nodes) sorts
    # cleanly. A back edge (grey node) is a cycle -- fail loud, never guess.
    by_id = {n.id: n for n in nodes}
    state: dict[str, int] = {}  # 1 = visiting, 2 = done
    order: list[Node] = []

    def visit(node: Node) -> None:
        s = state.get(node.id)
        if s == 2:
            return
        if s == 1:
            raise ValueError(f"cycle in workflow graph at node {node.id!r}")
        state[node.id] = 1
        for dep in node.trigger.after:
            if dep in by_id:
                visit(by_id[dep])
        state[node.id] = 2
        order.append(node)

    for node in nodes:
        visit(node)
    return order
