from __future__ import annotations

from dataclasses import dataclass

from mypipeline.workflows import Node, default_workflows, topo_sort


# One immediate (run-cli) step the driver ticks, in dependency order. The graph
# owns which stages run and in what order; the driver (my-fleet) binds `stage`
# to concrete argv at run time. `engine` is the declared cost, surfaced so the
# total spend of a cycle is readable off the plan.
@dataclass(frozen=True)
class PlanItem:
    node_id: str
    stage: str
    engine: str


def build_waves(workflows: list[Node] | None = None) -> list[list[PlanItem]]:
    # A wave is a set of nodes whose `after` dependencies are all satisfied by
    # earlier waves and not by each other — the graph's actual independence,
    # not just the flat order convenient for a single-threaded driver walk.
    # Layer = 1 + the deepest dependency's layer (0 for a node with none);
    # topo_sort's own post-order guarantees a node's deps are already layered
    # by the time we reach it, since deps are appended to its output first.
    nodes = workflows if workflows is not None else default_workflows()
    run_cli = [n for n in nodes if n.action.type == "run-cli"]
    ordered = topo_sort(run_cli)
    layer: dict[str, int] = {}
    for node in ordered:
        deps = [d for d in node.trigger.after if d in layer]
        layer[node.id] = 1 + max((layer[d] for d in deps), default=-1)

    waves: dict[int, list[Node]] = {}
    for node in ordered:
        waves.setdefault(layer[node.id], []).append(node)
    return [
        [PlanItem(n.id, n.action.stage, n.engine) for n in waves[k]] for k in sorted(waves)
    ]


def build_plan(workflows: list[Node] | None = None) -> list[PlanItem]:
    return [item for wave in build_waves(workflows) for item in wave]
