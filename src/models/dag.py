from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class DAGNode:
    # basic block for our dependency graph
    id: str
    title: str
    description: str
    target_files: list[str]
    # default to empty so we don't have to constantly pass it in
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class TaskDAG:
    # wrap the nodes up so it's easy to pass around
    nodes: list[DAGNode]

    def to_dict(self) -> dict:
        return {"nodes": [node.to_dict() for node in self.nodes]}
