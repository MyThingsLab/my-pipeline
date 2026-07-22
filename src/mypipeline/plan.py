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


def build_plan(workflows: list[Node] | None = None) -> list[PlanItem]:
    nodes = workflows if workflows is not None else default_workflows()
    run_cli = [n for n in nodes if n.action.type == "run-cli"]
    return [PlanItem(n.id, n.action.stage, n.engine) for n in topo_sort(run_cli)]
