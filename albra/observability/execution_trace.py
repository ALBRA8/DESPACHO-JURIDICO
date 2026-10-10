"""
EXECUTION TRACE - trazabilidad completa de cada ejecución.

Inspirado en NEX-SCOPE/src/lib/agent/trace.ts y AGENTE-TRADING observability.

Cada ejecución del agente queda persistida con:
- execution_id (estable, único)
- agent_id
- task
- requester (user)
- start, end
- tools invocados (con ok/error)
- skills/providers usados
- inputs, outputs
- decisions
- errors
- evidence_ids
- approvals
- costs
- status (running/completed/error/aborted)

CRÍTICO: cualquier ejecución puede reconstruirse mediante execution_id.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


class ExecutionTrace:
    """Trace persistido en sqlite."""

    def __init__(self, db_path: str = "./data/execution_trace.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.execution_trace")
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS execution_traces (
                execution_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                task TEXT NOT NULL,
                requester TEXT,
                start_ts REAL NOT NULL,
                end_ts REAL,
                status TEXT NOT NULL DEFAULT 'running',
                tools_json TEXT,
                providers_json TEXT,
                inputs_json TEXT,
                outputs_json TEXT,
                decisions_json TEXT,
                errors_json TEXT,
                evidence_ids_json TEXT,
                approvals_json TEXT,
                costs_json TEXT,
                metadata_json TEXT
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_et_status ON execution_traces(status)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_et_requester ON execution_traces(requester)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_et_start ON execution_traces(start_ts DESC)"
        )
        self._conn.commit()

    def start(
        self,
        *,
        agent_id: str,
        task: str,
        requester: str = "unknown",
        inputs: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        execution_id = uuid.uuid4().hex[:20]
        now = time.time()
        # 17 columnas (incluye end_ts=NULL al inicio)
        self._conn.execute(
            """
            INSERT INTO execution_traces
            (execution_id, agent_id, task, requester, start_ts, end_ts, status,
             tools_json, providers_json, inputs_json, outputs_json,
             decisions_json, errors_json, evidence_ids_json, approvals_json,
             costs_json, metadata_json)
            VALUES (?, ?, ?, ?, ?, NULL, 'running', '[]', '[]', ?, '[]', '[]', '[]', '[]', '[]', '{}', ?)
            """,
            (
                execution_id,
                agent_id,
                task,
                requester,
                now,
                json.dumps(inputs or {}, default=str),
                json.dumps(metadata or {}, default=str),
            ),
        )
        self._conn.commit()
        self.log.info("execution.start", execution_id=execution_id, task=task[:60])
        return execution_id

    def append_tool_call(
        self,
        execution_id: str,
        *,
        name: str,
        args: dict[str, Any] | None = None,
        ok: bool,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        entry = {
            "name": name,
            "args": args or {},
            "ok": ok,
            "result": str(result)[:500] if result is not None else None,
            "error": error,
            "ts": time.time(),
        }
        cur = self._conn.execute(
            "SELECT tools_json FROM execution_traces WHERE execution_id = ?",
            (execution_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        tools = json.loads(row[0]) if row[0] else []
        tools.append(entry)
        self._conn.execute(
            "UPDATE execution_traces SET tools_json = ? WHERE execution_id = ?",
            (json.dumps(tools, default=str), execution_id),
        )
        self._conn.commit()

    def append_provider(self, execution_id: str, *, provider: str, prompt_size: int = 0, response_size: int = 0) -> None:
        cur = self._conn.execute(
            "SELECT providers_json FROM execution_traces WHERE execution_id = ?",
            (execution_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        providers = json.loads(row[0]) if row[0] else []
        providers.append({
            "provider": provider,
            "prompt_size": prompt_size,
            "response_size": response_size,
            "ts": time.time(),
        })
        self._conn.execute(
            "UPDATE execution_traces SET providers_json = ? WHERE execution_id = ?",
            (json.dumps(providers, default=str), execution_id),
        )
        self._conn.commit()

    def append_evidence(self, execution_id: str, evidence_id: str) -> None:
        cur = self._conn.execute(
            "SELECT evidence_ids_json FROM execution_traces WHERE execution_id = ?",
            (execution_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        eids = json.loads(row[0]) if row[0] else []
        if evidence_id not in eids:
            eids.append(evidence_id)
            self._conn.execute(
                "UPDATE execution_traces SET evidence_ids_json = ? WHERE execution_id = ?",
                (json.dumps(eids), execution_id),
            )
            self._conn.commit()

    def append_approval(self, execution_id: str, *, approval_id: str, action: str, status: str) -> None:
        cur = self._conn.execute(
            "SELECT approvals_json FROM execution_traces WHERE execution_id = ?",
            (execution_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        approvals = json.loads(row[0]) if row[0] else []
        approvals.append({
            "approval_id": approval_id,
            "action": action,
            "status": status,
            "ts": time.time(),
        })
        self._conn.execute(
            "UPDATE execution_traces SET approvals_json = ? WHERE execution_id = ?",
            (json.dumps(approvals, default=str), execution_id),
        )
        self._conn.commit()

    def record_cost(self, execution_id: str, *, tokens_in: int = 0, tokens_out: int = 0, usd: float = 0.0) -> None:
        cur = self._conn.execute(
            "SELECT costs_json FROM execution_traces WHERE execution_id = ?",
            (execution_id,),
        )
        row = cur.fetchone()
        if not row:
            return
        costs = json.loads(row[0]) if row[0] else {}
        costs["tokens_in"] = costs.get("tokens_in", 0) + tokens_in
        costs["tokens_out"] = costs.get("tokens_out", 0) + tokens_out
        costs["usd"] = round(costs.get("usd", 0.0) + usd, 6)
        self._conn.execute(
            "UPDATE execution_traces SET costs_json = ? WHERE execution_id = ?",
            (json.dumps(costs), execution_id),
        )
        self._conn.commit()

    def finish(
        self,
        execution_id: str,
        *,
        status: str = "completed",
        outputs: dict[str, Any] | None = None,
        errors: list[str] | None = None,
        decisions: list[dict[str, Any]] | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE execution_traces
            SET end_ts = ?, status = ?, outputs_json = ?, errors_json = ?, decisions_json = ?
            WHERE execution_id = ?
            """,
            (
                time.time(),
                status,
                json.dumps(outputs or {}, default=str),
                json.dumps(errors or [], default=str),
                json.dumps(decisions or [], default=str),
                execution_id,
            ),
        )
        self._conn.commit()
        self.log.info("execution.finish", execution_id=execution_id, status=status)

    def get(self, execution_id: str) -> dict[str, Any] | None:
        cur = self._conn.execute(
            "SELECT * FROM execution_traces WHERE execution_id = ?",
            (execution_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        result = dict(zip(cols, row, strict=False))
        # Desempaquetar JSONs
        for k in [c for c in cols if c.endswith("_json")]:
            field = k.replace("_json", "")
            try:
                result[field] = json.loads(result[k]) if result[k] else None
            except json.JSONDecodeError:
                result[field] = None
            del result[k]
        return result

    def list_recent(self, *, limit: int = 20, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            cur = self._conn.execute(
                "SELECT execution_id, agent_id, task, requester, start_ts, end_ts, status "
                "FROM execution_traces WHERE status = ? "
                "ORDER BY start_ts DESC LIMIT ?",
                (status, limit),
            )
        else:
            cur = self._conn.execute(
                "SELECT execution_id, agent_id, task, requester, start_ts, end_ts, status "
                "FROM execution_traces ORDER BY start_ts DESC LIMIT ?",
                (limit,),
            )
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r, strict=False)) for r in rows]

    def stats(self) -> dict[str, Any]:
        cur = self._conn.execute(
            "SELECT status, COUNT(*) FROM execution_traces GROUP BY status"
        )
        by_status = {r[0]: r[1] for r in cur.fetchall()}
        return {"total": sum(by_status.values()), "by_status": by_status}

    def close(self) -> None:
        if self._conn:
            self._conn.close()
