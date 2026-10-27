"""
MATTER AUDIT — JSONL append-only por matter con hash chain tamper-evident.

Cada acción (del agente o del abogado) queda registrada en
``data/matters/<matter_id>/audit.jsonl`` con:
- timestamp ISO 8601 UTC
- actor (user_id o agent_name)
- authority (role/permission del actor)
- model (si es LLM, el modelo usado; vacío si no)
- action_type
- action_payload (dict)
- result (dict)
- prev_hash (hash del entry anterior — cadena SHA-256)
- this_hash (hash del entry actual + prev_hash)

REGLA CRÍTICA (ética abogadil colombiana):
- Modificar un entry rompe la cadena (detectable con verify_chain()).
- Cualquier auditor externo puede verificar la integridad del expediente.
- Retención configurable (default 10 años alineado con expectativa de
  colegiación y Tribunal Nacional Disciplinario).

Diferencia con albra.audit.tamper_evident.TamperEvidentAudit:
- TamperEvidentAudit es global (un solo audit.log para todo el agente).
- MatterAudit es por-matter (cada expediente tiene su propio audit.jsonl).
- MatterAudit añade campos específicos: action_type, action_payload,
  authority, model.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MatterAudit:
    """Audit log JSONL append-only por matter con hash chain."""

    GENESIS_HASH = "0" * 64

    def __init__(self, matters_dir: str = "./data/matters") -> None:
        self.matters_dir = Path(matters_dir)
        self.matters_dir.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.audit.matter_audit")
        # Cache del último hash por matter (para no releer el archivo)
        self._last_hash_cache: dict[str, str] = {}

    def _matter_dir(self, matter_id: str) -> Path:
        d = self.matters_dir / matter_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _audit_path(self, matter_id: str) -> Path:
        return self._matter_dir(matter_id) / "audit.jsonl"

    def _load_last_hash(self, matter_id: str) -> str:
        """Lee el último hash del archivo de audit del matter."""
        if matter_id in self._last_hash_cache:
            return self._last_hash_cache[matter_id]
        path = self._audit_path(matter_id)
        last = self.GENESIS_HASH
        if path.exists():
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        last = entry.get("this_hash", last)
                    except json.JSONDecodeError:
                        continue
        self._last_hash_cache[matter_id] = last
        return last

    def append(
        self,
        matter_id: str,
        *,
        actor: str,
        authority: str = "",
        model: str = "",
        action_type: str,
        action_payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append una entrada al audit log del matter.

        Devuelve el entry completo (incluyendo this_hash).
        """
        ts = _utcnow_iso()
        prev_hash = self._load_last_hash(matter_id)
        # Block a firmar: TODO menos this_hash
        block = {
            "ts": ts,
            "actor": actor,
            "authority": authority,
            "model": model,
            "action_type": action_type,
            "action_payload": action_payload or {},
            "result": result or {},
            "prev_hash": prev_hash,
        }
        block_str = json.dumps(block, sort_keys=True, ensure_ascii=False, default=str)
        this_hash = hashlib.sha256(block_str.encode("utf-8")).hexdigest()
        block["this_hash"] = this_hash

        path = self._audit_path(matter_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(block, ensure_ascii=False, default=str) + "\n")

        self._last_hash_cache[matter_id] = this_hash
        self.log.debug(
            "audit.matter_append",
            matter_id=matter_id,
            action_type=action_type,
            hash=this_hash[:12],
        )
        return block

    def verify_chain(self, matter_id: str) -> dict[str, Any]:
        """Verifica integridad del hash chain del matter.

        Returns:
            {ok: bool, total: int, broken_at: list[int]}
            - ok=True si no fue manipulado
            - broken_at: índices de entries donde la cadena se rompe
        """
        path = self._audit_path(matter_id)
        if not path.exists():
            return {"ok": True, "total": 0, "broken_at": [], "matter_id": matter_id}

        prev = self.GENESIS_HASH
        total = 0
        broken_at: list[int] = []

        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    broken_at.append(i)
                    continue
                expected_prev = entry.get("prev_hash")
                this_hash = entry.get("this_hash")
                # Verificar prev_hash encadena con entry anterior
                if expected_prev != prev:
                    broken_at.append(i)
                    prev = this_hash or prev
                    continue
                # Verificar this_hash (recomputar)
                block_copy = {k: v for k, v in entry.items() if k != "this_hash"}
                block_str = json.dumps(
                    block_copy, sort_keys=True, ensure_ascii=False, default=str
                )
                expected_hash = hashlib.sha256(block_str.encode("utf-8")).hexdigest()
                if expected_hash != this_hash:
                    broken_at.append(i)
                prev = this_hash or prev
                total += 1

        return {
            "ok": len(broken_at) == 0,
            "total": total,
            "broken_at": broken_at,
            "matter_id": matter_id,
        }

    def read(
        self,
        matter_id: str,
        *,
        action_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Lee entries del audit log del matter."""
        path = self._audit_path(matter_id)
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if action_type and e.get("action_type") != action_type:
                        continue
                    entries.append(e)
                except json.JSONDecodeError:
                    continue
        if limit:
            entries = entries[-limit:]
        return entries

    def count(self, matter_id: str) -> int:
        path = self._audit_path(matter_id)
        if not path.exists():
            return 0
        c = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c += 1
        return c

    def fingerprint(self, matter_id: str) -> str:
        """Hash del archivo completo — útil para comparar con backups."""
        path = self._audit_path(matter_id)
        if not path.exists():
            return ""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def export(self, matter_id: str) -> dict[str, Any]:
        """Exporta el audit log completo + verificación de cadena.

        Útil para auditoría externa o para sellar criptográficamente (V2.1).
        """
        return {
            "matter_id": matter_id,
            "entries": self.read(matter_id),
            "verification": self.verify_chain(matter_id),
            "fingerprint": self.fingerprint(matter_id),
            "exported_at": _utcnow_iso(),
            "total_entries": self.count(matter_id),
        }
