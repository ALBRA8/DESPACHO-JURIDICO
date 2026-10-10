"""
Graph Workflows - flujos como grafos dirigidos con ciclos
y interrupts HITL.

Nodos: funciones async que reciben state y devuelven delta.
Edges: transiciones condicionales.
Interrupts: puntos donde el flujo pausa para aprobación humana.

Permite representar workflows jurídicos complejos como:
- demanda → contestación → pruebas → alegatos → sentencia
- con ciclos (apelaciones) e interrupts (firmas, presentaciones)
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from albra.events.bus import EventBus
from albra.observability.logger import get_logger


class NodeKind(str, Enum):
    ACTION = "action"
    DECISION = "decision"
    INTERRUPT = "interrupt"
    TERMINAL = "terminal"


StateFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
EdgeCond = Callable[[dict[str, Any]], str | None]


@dataclass
class GraphNode:
    name: str
    kind: NodeKind
    fn: StateFn | None = None
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    src: str
    dst: str
    cond: EdgeCond | None = None
    label: str = ""


@dataclass
class GraphRun:
    id: str
    state: dict[str, Any]
    current: str | None
    status: str  # running | interrupted | done | error
    visited: list[str] = field(default_factory=list)
    interrupted_at: str | None = None
    error: str | None = None


class WorkflowGraph:
    """Grafo dirigido stateful."""

    def __init__(self, name: str, *, event_bus: EventBus | None = None) -> None:
        self.name = name
        self.log = get_logger(f"albra.workflow.graph.{name}")
        self._event_bus = event_bus
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, list[GraphEdge]] = {}
        self._entry: str | None = None
        self._runs: dict[str, GraphRun] = {}

    def add_node(self, node: GraphNode) -> WorkflowGraph:
        if node.name in self._nodes:
            raise ValueError(f"Node '{node.name}' ya existe")
        self._nodes[node.name] = node
        if self._entry is None:
            self._entry = node.name
        return self

    def add_edge(self, src: str, dst: str, *, cond: EdgeCond | None = None, label: str = "") -> WorkflowGraph:
        if src not in self._nodes:
            raise ValueError(f"Source node '{src}' no existe")
        if dst not in self._nodes:
            raise ValueError(f"Target node '{dst}' no existe")
        self._edges.setdefault(src, []).append(GraphEdge(src, dst, cond, label))
        return self

    def entry(self, name: str) -> WorkflowGraph:
        if name not in self._nodes:
            raise ValueError(f"Node '{name}' no existe")
        self._entry = name
        return self

    async def run(self, initial_state: dict[str, Any] | None = None) -> GraphRun:
        import uuid
        run_id = uuid.uuid4().hex[:12]
        run = GraphRun(
            id=run_id,
            state=dict(initial_state or {}),
            current=self._entry,
            status="running",
        )
        self._runs[run_id] = run
        await self._execute(run)
        return run

    async def resume(self, run_id: str, *, approved: bool = True) -> GraphRun:
        run = self._runs.get(run_id)
        if not run or run.status != "interrupted":
            raise ValueError(f"Run {run_id} no está interrumpido")
        run.state["__approved__"] = approved
        run.status = "running"
        # Saltar al siguiente nodo después del interrupt
        await self._advance(run)
        await self._execute(run)
        return run

    async def _execute(self, run: GraphRun) -> None:
        while run.status == "running" and run.current is not None:
            node = self._nodes.get(run.current)
            if not node:
                run.status = "error"
                run.error = f"Node '{run.current}' no existe"
                return
            run.visited.append(run.current)

            # Emitir evento de step
            if self._event_bus:
                await self._event_bus.emit(
                    "workflow.graph.step",
                    {"run": run.id, "node": run.current, "kind": node.kind.value},
                )

            if node.kind == NodeKind.TERMINAL:
                run.status = "done"
                return

            if node.kind == NodeKind.INTERRUPT:
                run.status = "interrupted"
                run.interrupted_at = run.current
                self.log.info("graph.interrupt", run=run.id, node=run.current)
                return

            if node.fn:
                try:
                    delta = await node.fn(run.state)
                    if delta:
                        run.state.update(delta)
                except Exception as e:  # noqa: BLE001
                    run.status = "error"
                    run.error = str(e)
                    return

            await self._advance(run)

    async def _advance(self, run: GraphRun) -> None:
        edges = self._edges.get(run.current, [])
        next_node: str | None = None
        for edge in edges:
            if edge.cond:
                try:
                    decision = edge.cond(run.state)
                    if decision:
                        next_node = decision
                        break
                except Exception:  # noqa: BLE001
                    continue
            else:
                next_node = edge.dst
                break
        run.current = next_node
        if next_node is None:
            run.status = "done"

    def runs(self) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "status": r.status,
                "current": r.current,
                "interrupted_at": r.interrupted_at,
                "visited": r.visited,
                "error": r.error,
                "state_keys": list(r.state.keys()),
            }
            for r in self._runs.values()
        ]


# --- Builder de workflows jurídicos comunes ---

def build_demand_workflow(*, event_bus: EventBus | None = None) -> WorkflowGraph:
    """Workflow típico de presentación de demanda."""
    g = WorkflowGraph("demanda_judicial", event_bus=event_bus)

    async def _gather(state):
        return {"phase": "recopilacion"}

    async def _draft(state):
        return {"phase": "redaccion"}

    async def _review(state):
        return {"phase": "revision_interna"}

    async def _approve(state):
        return {"phase": "esperando_aprobacion"}

    async def _file(state):
        return {"phase": "presentada"}

    g.add_node(GraphNode("gather", NodeKind.ACTION, _gather, "Recopilar hechos y pruebas"))
    g.add_node(GraphNode("draft", NodeKind.ACTION, _draft, "Redactar demanda"))
    g.add_node(GraphNode("review", NodeKind.ACTION, _review, "Revisión interna del despacho"))
    g.add_node(GraphNode("approve", NodeKind.INTERRUPT, _approve, "Aprobación HITL del cliente"))
    g.add_node(GraphNode("file", NodeKind.ACTION, _file, "Presentar ante juzgado"))
    g.add_node(GraphNode("done", NodeKind.TERMINAL, None, "Fin"))

    g.entry("gather")
    g.add_edge("gather", "draft")
    g.add_edge("draft", "review")
    g.add_edge("review", "approve")
    g.add_edge("approve", "file")
    g.add_edge("file", "done")
    # Si review falla, vuelve a gather
    g.add_edge("review", "gather", cond=lambda s: s.get("phase") == "revision_interna" and s.get("needs_rework"))
    return g
