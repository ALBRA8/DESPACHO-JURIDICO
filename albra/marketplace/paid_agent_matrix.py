"""
X402 PAID-AGENT MATRIX — monetización por skill con USDC settlement.

Inspiración clean-room: GLAW pattern (X402 paid-agent matrix: cada skill
es un agente facturable con service matrix). Implementación V2.5-C local
(sin integración USDC real; V2.6+: integración con Coinbase Commerce o
Circle USDC API).

Concepto:
- Cada skill del marketplace tiene un service_matrix:
  - price_per_call_usd: float (precio por invocación)
  - price_per_month_usd: float (precio suscripción mensual)
  - free_tier_calls_per_month: int (calls gratis antes de cobrar)
  - payment_address_usdc: str (dirección USDC, opcional V2.5-C)
- Cuando un tenant invoca una skill, se registra una usage record.
- Si la invocación supera free_tier → se factura.
- Billing cycle mensual. Estado: pending | billed | paid | overdue.

V2.5-C: matriz en SQLite local, sin settlement real.
V2.6+: integración USDC + webhook Coinbase Commerce.

Tablas:
    service_matrix (pricing per skill):
        skill_id TEXT PRIMARY KEY REFERENCES marketplace skills
        price_per_call_usd REAL NOT NULL DEFAULT 0.0
        price_per_month_usd REAL NOT NULL DEFAULT 0.0
        free_tier_calls_per_month INTEGER NOT NULL DEFAULT 100
        payment_address_usdc TEXT (default '')
        active BOOLEAN NOT NULL DEFAULT 1

    usage_records:
        id TEXT PRIMARY KEY (UUID)
        tenant_id TEXT NOT NULL
        skill_id TEXT NOT NULL
        called_at TEXT NOT NULL (ISO)
        billed BOOLEAN NOT NULL DEFAULT 0
        amount_usd REAL NOT NULL DEFAULT 0.0
        status TEXT NOT NULL DEFAULT 'pending'  -- pending|billed|paid|overdue

    billing_cycles:
        id TEXT PRIMARY KEY
        tenant_id TEXT NOT NULL
        period_start TEXT NOT NULL
        period_end TEXT NOT NULL
        total_usd REAL NOT NULL DEFAULT 0.0
        status TEXT NOT NULL DEFAULT 'open'  -- open|invoiced|paid|overdue
        invoice_url TEXT (default '')
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from albra.observability.logger import get_logger

# ===== Block N — explicit billing vs settlement separation =====
# Billing status: estado del ciclo de facturación desde el punto de vista del
# cobro al cliente (¿se emitió factura? ¿se pagó? ¿venció?).
BILLING_STATUS: frozenset[str] = frozenset({"pending", "billed", "overdue"})
# (Note: legacy BillingCycle.status uses "open"/"invoiced"/"paid"/"overdue"
# for backward compatibility with V2.5-C — these map conceptually to the
# BILLING_STATUS lifecycle. New code SHOULD distinguish billing from
# settlement explicitly.)
# Settlement status: estado del settlement on-chain (USDC tx). ¿Se envió la
# transacción? ¿Se confirmó? ¿Falló? SEPARATE concern from billing — a cycle
# may be "billed" (invoice sent) but "unsettled" (no USDC tx confirmed yet).
SETTLEMENT_STATUS: frozenset[str] = frozenset({"unsettled", "settled", "failed"})


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ServiceMatrix:
    """Pricing de una skill en el marketplace."""
    skill_id: str
    price_per_call_usd: float = 0.0
    price_per_month_usd: float = 0.0
    free_tier_calls_per_month: int = 100
    payment_address_usdc: str = ""
    active: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "price_per_call_usd": self.price_per_call_usd,
            "price_per_month_usd": self.price_per_month_usd,
            "free_tier_calls_per_month": self.free_tier_calls_per_month,
            "payment_address_usdc": self.payment_address_usdc,
            "active": self.active,
        }


@dataclass
class UsageRecord:
    """Registro de una invocación de skill por un tenant."""
    id: str
    tenant_id: str
    skill_id: str
    called_at: str
    billed: bool = False
    amount_usd: float = 0.0
    status: str = "pending"  # pending | billed | paid | overdue

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "skill_id": self.skill_id,
            "called_at": self.called_at,
            "billed": self.billed,
            "amount_usd": self.amount_usd,
            "status": self.status,
        }


@dataclass
class BillingCycle:
    """Ciclo de facturación mensual de un tenant.

    Block N: billing status (legacy `status` field, backward-compat with
    V2.5-C: open | invoiced | paid | overdue) and settlement status
    (`settlement_status`: unsettled | settled | failed) are SEPARATE concerns.
    A cycle may be `status="paid"` (client paid the invoice) but
    `settlement_status="unsettled"` (USDC tx not yet confirmed on-chain).
    `mark_paid` does NOT auto-mark settled — `mark_settled(tx_hash)` must be
    called explicitly when the USDC transaction is confirmed.
    """
    id: str
    tenant_id: str
    period_start: str
    period_end: str
    total_usd: float = 0.0
    status: str = "open"  # open | invoiced | paid | overdue  (billing lifecycle)
    invoice_url: str = ""
    # Block N — separate settlement concern (USDC on-chain settlement)
    settlement_status: str = "unsettled"
    settlement_tx_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "total_usd": self.total_usd,
            "status": self.status,
            "invoice_url": self.invoice_url,
            "settlement_status": self.settlement_status,
            "settlement_tx_hash": self.settlement_tx_hash,
        }


class PaidAgentMatrix:
    """Matriz de pagos para skills con USDC settlement.

    V2.5-C: registro local sin integración USDC real.
    V2.6+: integración Coinbase Commerce / Circle USDC API.
    """

    def __init__(self, db_path: str = "./data/paid_agent_matrix.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = get_logger("albra.marketplace.paid_agent_matrix")
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS service_matrix (
                skill_id TEXT PRIMARY KEY,
                price_per_call_usd REAL NOT NULL DEFAULT 0.0,
                price_per_month_usd REAL NOT NULL DEFAULT 0.0,
                free_tier_calls_per_month INTEGER NOT NULL DEFAULT 100,
                payment_address_usdc TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS usage_records (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                skill_id TEXT NOT NULL,
                called_at TEXT NOT NULL,
                billed INTEGER NOT NULL DEFAULT 0,
                amount_usd REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'pending'
            );

            CREATE TABLE IF NOT EXISTS billing_cycles (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                total_usd REAL NOT NULL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'open',
                invoice_url TEXT NOT NULL DEFAULT '',
                settlement_status TEXT NOT NULL DEFAULT 'unsettled',
                settlement_tx_hash TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_usage_tenant ON usage_records(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_usage_skill ON usage_records(skill_id);
            CREATE INDEX IF NOT EXISTS idx_usage_status ON usage_records(status);
            CREATE INDEX IF NOT EXISTS idx_billing_tenant ON billing_cycles(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_billing_status ON billing_cycles(status);
            CREATE INDEX IF NOT EXISTS idx_billing_settlement
                ON billing_cycles(settlement_status);
            """
        )
        # Block N migration — add settlement columns to pre-existing DBs.
        cur_mig = self._conn.execute("PRAGMA table_info(billing_cycles)")
        existing_cols = {row[1] for row in cur_mig.fetchall()}
        for col, ddl in (
            ("settlement_status", "TEXT NOT NULL DEFAULT 'unsettled'"),
            ("settlement_tx_hash", "TEXT NOT NULL DEFAULT ''"),
        ):
            if col not in existing_cols:
                self._conn.execute(
                    f"ALTER TABLE billing_cycles ADD COLUMN {col} {ddl}"
                )
        self._conn.commit()

    # ===== Service matrix =====

    def set_pricing(
        self,
        *,
        skill_id: str,
        price_per_call_usd: float = 0.0,
        price_per_month_usd: float = 0.0,
        free_tier_calls_per_month: int = 100,
        payment_address_usdc: str = "",
        active: bool = True,
    ) -> ServiceMatrix:
        """Configura el pricing de una skill. Insert o update (idempotente)."""
        existing = self.get_pricing(skill_id)
        if existing:
            self._conn.execute(
                """
                UPDATE service_matrix
                SET price_per_call_usd = ?, price_per_month_usd = ?,
                    free_tier_calls_per_month = ?, payment_address_usdc = ?,
                    active = ?
                WHERE skill_id = ?
                """,
                (
                    price_per_call_usd, price_per_month_usd,
                    free_tier_calls_per_month, payment_address_usdc,
                    1 if active else 0,
                    skill_id,
                ),
            )
        else:
            self._conn.execute(
                """
                INSERT INTO service_matrix
                (skill_id, price_per_call_usd, price_per_month_usd,
                 free_tier_calls_per_month, payment_address_usdc, active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id, price_per_call_usd, price_per_month_usd,
                    free_tier_calls_per_month, payment_address_usdc,
                    1 if active else 0,
                ),
            )
        self._conn.commit()
        self.log.info(
            "paid_agent_matrix.pricing_set", skill_id=skill_id,
            price_per_call=price_per_call_usd,
            price_per_month=price_per_month_usd,
        )
        return ServiceMatrix(
            skill_id=skill_id,
            price_per_call_usd=price_per_call_usd,
            price_per_month_usd=price_per_month_usd,
            free_tier_calls_per_month=free_tier_calls_per_month,
            payment_address_usdc=payment_address_usdc,
            active=active,
        )

    def get_pricing(self, skill_id: str) -> ServiceMatrix | None:
        cur = self._conn.execute(
            "SELECT skill_id, price_per_call_usd, price_per_month_usd, "
            "free_tier_calls_per_month, payment_address_usdc, active "
            "FROM service_matrix WHERE skill_id = ?",
            (skill_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return ServiceMatrix(
            skill_id=row[0],
            price_per_call_usd=row[1],
            price_per_month_usd=row[2],
            free_tier_calls_per_month=row[3],
            payment_address_usdc=row[4],
            active=bool(row[5]),
        )

    def deactivate_pricing(self, skill_id: str) -> bool:
        if self.get_pricing(skill_id) is None:
            return False
        self._conn.execute(
            "UPDATE service_matrix SET active = 0 WHERE skill_id = ?",
            (skill_id,),
        )
        self._conn.commit()
        return True

    # ===== Usage tracking =====

    def record_usage(
        self,
        *,
        tenant_id: str,
        skill_id: str,
    ) -> UsageRecord:
        """Registra una invocación de skill por un tenant.

        Calcula el amount_usd basado en:
        - Si tenant está dentro de free_tier → amount_usd = 0, billed=False
        - Si excede free_tier → amount_usd = price_per_call_usd, billed=False
          (se factura al cierre del ciclo)
        """
        pricing = self.get_pricing(skill_id)
        if not pricing or not pricing.active:
            # Skill sin pricing o inactiva → uso gratis (no se factura)
            amount = 0.0
            free_tier_used = False
        else:
            # Contar usos este mes
            now = datetime.now(timezone.utc)
            period_start = now.replace(day=1, hour=0, minute=0, second=0)
            period_end = (period_start + timedelta(days=32)).replace(day=1)
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM usage_records "
                "WHERE tenant_id = ? AND skill_id = ? "
                "AND called_at >= ? AND called_at < ?",
                (
                    tenant_id, skill_id,
                    period_start.isoformat(timespec="seconds"),
                    period_end.isoformat(timespec="seconds"),
                ),
            )
            count_this_month = cur.fetchone()[0]
            free_tier_used = count_this_month < pricing.free_tier_calls_per_month
            amount = 0.0 if free_tier_used else pricing.price_per_call_usd

        record = UsageRecord(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            skill_id=skill_id,
            called_at=_utcnow_iso(),
            billed=False,
            amount_usd=amount,
            status="pending",
        )
        self._conn.execute(
            """
            INSERT INTO usage_records
            (id, tenant_id, skill_id, called_at, billed, amount_usd, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id, record.tenant_id, record.skill_id,
                record.called_at,
                0 if not record.billed else 1,
                record.amount_usd, record.status,
            ),
        )
        self._conn.commit()
        self.log.info(
            "paid_agent_matrix.usage_recorded",
            tenant_id=tenant_id, skill_id=skill_id,
            amount=amount, free_tier=free_tier_used,
        )
        return record

    def list_usage(
        self,
        *,
        tenant_id: str | None = None,
        skill_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[UsageRecord]:
        q = "SELECT id, tenant_id, skill_id, called_at, billed, amount_usd, status FROM usage_records WHERE 1=1"
        args: list[Any] = []
        if tenant_id:
            q += " AND tenant_id = ?"
            args.append(tenant_id)
        if skill_id:
            q += " AND skill_id = ?"
            args.append(skill_id)
        if status:
            q += " AND status = ?"
            args.append(status)
        q += " ORDER BY called_at DESC LIMIT ?"
        args.append(limit)
        cur = self._conn.execute(q, args)
        return [
            UsageRecord(
                id=r[0], tenant_id=r[1], skill_id=r[2], called_at=r[3],
                billed=bool(r[4]), amount_usd=r[5], status=r[6],
            )
            for r in cur.fetchall()
        ]

    # ===== Billing cycles =====

    def get_or_create_billing_cycle(
        self, tenant_id: str, period_start_iso: str | None = None
    ) -> BillingCycle:
        """Crea o retorna el ciclo de facturación actual del tenant."""
        if period_start_iso is None:
            now = datetime.now(timezone.utc)
            period_start_dt = now.replace(day=1, hour=0, minute=0, second=0)
            period_end_dt = (period_start_dt + timedelta(days=32)).replace(day=1)
        else:
            period_start_dt = datetime.fromisoformat(period_start_iso)
            period_end_dt = period_start_dt + timedelta(days=30)
        period_start_iso = period_start_dt.isoformat(timespec="seconds")
        period_end_iso = period_end_dt.isoformat(timespec="seconds")

        # Buscar ciclo existente
        cur = self._conn.execute(
            "SELECT id, tenant_id, period_start, period_end, total_usd, status, "
            "invoice_url, settlement_status, settlement_tx_hash "
            "FROM billing_cycles WHERE tenant_id = ? AND period_start = ?",
            (tenant_id, period_start_iso),
        )
        row = cur.fetchone()
        if row:
            return BillingCycle(
                id=row[0], tenant_id=row[1], period_start=row[2],
                period_end=row[3], total_usd=row[4], status=row[5],
                invoice_url=row[6], settlement_status=row[7],
                settlement_tx_hash=row[8],
            )
        # Crear nuevo ciclo
        cycle_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO billing_cycles
            (id, tenant_id, period_start, period_end, total_usd, status,
             invoice_url, settlement_status, settlement_tx_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cycle_id, tenant_id, period_start_iso, period_end_iso,
                0.0, "open", "", "unsettled", "",
            ),
        )
        self._conn.commit()
        return BillingCycle(
            id=cycle_id, tenant_id=tenant_id,
            period_start=period_start_iso, period_end=period_end_iso,
            total_usd=0.0, status="open", invoice_url="",
            settlement_status="unsettled", settlement_tx_hash="",
        )

    def close_billing_cycle(self, cycle_id: str) -> BillingCycle:
        """Cierra el ciclo: suma todos los usage records pending, marca billed."""
        cur = self._conn.execute(
            "SELECT tenant_id, period_start, period_end FROM billing_cycles WHERE id = ?",
            (cycle_id,),
        )
        row = cur.fetchone()
        if not row:
            raise KeyError(f"Billing cycle not found: {cycle_id}")
        tenant_id, period_start, period_end = row

        # Sum usage records pending en este período
        cur_usage = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0.0) FROM usage_records "
            "WHERE tenant_id = ? AND called_at >= ? AND called_at < ? AND billed = 0",
            (tenant_id, period_start, period_end),
        )
        total = cur_usage.fetchone()[0]

        # Marcar usage records como billed
        self._conn.execute(
            "UPDATE usage_records SET billed = 1, status = 'billed' "
            "WHERE tenant_id = ? AND called_at >= ? AND called_at < ? AND billed = 0",
            (tenant_id, period_start, period_end),
        )
        # Update billing cycle
        self._conn.execute(
            "UPDATE billing_cycles SET total_usd = ?, status = 'invoiced' WHERE id = ?",
            (total, cycle_id),
        )
        self._conn.commit()
        self.log.info(
            "paid_agent_matrix.cycle_closed", cycle_id=cycle_id,
            total_usd=total,
        )
        cur_updated = self._conn.execute(
            "SELECT id, tenant_id, period_start, period_end, total_usd, status, "
            "invoice_url, settlement_status, settlement_tx_hash "
            "FROM billing_cycles WHERE id = ?",
            (cycle_id,),
        )
        r = cur_updated.fetchone()
        return BillingCycle(
            id=r[0], tenant_id=r[1], period_start=r[2], period_end=r[3],
            total_usd=r[4], status=r[5], invoice_url=r[6],
            settlement_status=r[7], settlement_tx_hash=r[8],
        )

    def mark_paid(self, cycle_id: str, invoice_url: str = "") -> BillingCycle:
        """Marca un ciclo como pagado (billing-side — client paid the invoice).

        Block N: This ONLY updates the billing-side status (status="paid" +
        invoice_url). It does NOT touch settlement_status — a paid invoice
        is not the same as a confirmed USDC settlement. Callers must use
        `mark_settled(tx_hash)` separately when the on-chain USDC transaction
        is confirmed.
        """
        self._conn.execute(
            "UPDATE billing_cycles SET status = 'paid', invoice_url = ? WHERE id = ?",
            (invoice_url, cycle_id),
        )
        self._conn.commit()
        # Mark usage records as paid too (billing-side only).
        cur = self._conn.execute(
            "SELECT tenant_id, period_start, period_end FROM billing_cycles WHERE id = ?",
            (cycle_id,),
        )
        row = cur.fetchone()
        if row:
            tenant_id, period_start, period_end = row
            self._conn.execute(
                "UPDATE usage_records SET status = 'paid' "
                "WHERE tenant_id = ? AND called_at >= ? AND called_at < ?",
                (tenant_id, period_start, period_end),
            )
            self._conn.commit()
        # Return updated
        cur_updated = self._conn.execute(
            "SELECT id, tenant_id, period_start, period_end, total_usd, status, "
            "invoice_url, settlement_status, settlement_tx_hash "
            "FROM billing_cycles WHERE id = ?",
            (cycle_id,),
        )
        r = cur_updated.fetchone()
        return BillingCycle(
            id=r[0], tenant_id=r[1], period_start=r[2], period_end=r[3],
            total_usd=r[4], status=r[5], invoice_url=r[6],
            settlement_status=r[7], settlement_tx_hash=r[8],
        )

    def mark_settled(self, cycle_id: str, tx_hash: str) -> BillingCycle:
        """Marca el settlement del ciclo como confirmado on-chain (Block N).

        Esto es SEPARADO de mark_paid:
        - mark_paid: el cliente pagó la factura (billing-side status="paid").
        - mark_settled: la transacción USDC on-chain fue confirmada
          (settlement-side settlement_status="settled" + tx_hash).

        Un ciclo puede estar "paid" pero no "settled" (e.g. pago fiat pendiente
        de convertirse a USDC) o "settled" sin "paid" (e.g. settlement manual
        sin pasar por el flujo de invoice).

        Args:
            cycle_id: id del billing cycle.
            tx_hash: hash de la transacción USDC on-chain.

        Raises:
            KeyError: si el cycle_id no existe.
        """
        cur = self._conn.execute(
            "SELECT id FROM billing_cycles WHERE id = ?",
            (cycle_id,),
        )
        if cur.fetchone() is None:
            raise KeyError(f"Billing cycle not found: {cycle_id}")
        self._conn.execute(
            "UPDATE billing_cycles "
            "SET settlement_status = 'settled', settlement_tx_hash = ? "
            "WHERE id = ?",
            (tx_hash, cycle_id),
        )
        self._conn.commit()
        self.log.info(
            "paid_agent_matrix.cycle_settled",
            cycle_id=cycle_id, tx_hash=tx_hash,
        )
        cur_updated = self._conn.execute(
            "SELECT id, tenant_id, period_start, period_end, total_usd, status, "
            "invoice_url, settlement_status, settlement_tx_hash "
            "FROM billing_cycles WHERE id = ?",
            (cycle_id,),
        )
        r = cur_updated.fetchone()
        return BillingCycle(
            id=r[0], tenant_id=r[1], period_start=r[2], period_end=r[3],
            total_usd=r[4], status=r[5], invoice_url=r[6],
            settlement_status=r[7], settlement_tx_hash=r[8],
        )

    # ===== Stats =====

    def stats(self) -> dict[str, Any]:
        cur_p = self._conn.execute("SELECT COUNT(*) FROM service_matrix")
        total_pricings = cur_p.fetchone()[0]
        cur_u = self._conn.execute("SELECT COUNT(*) FROM usage_records")
        total_usage = cur_u.fetchone()[0]
        cur_b = self._conn.execute("SELECT COUNT(*) FROM billing_cycles")
        total_cycles = cur_b.fetchone()[0]
        cur_revenue = self._conn.execute(
            "SELECT COALESCE(SUM(total_usd), 0.0) FROM billing_cycles WHERE status = 'paid'"
        )
        total_revenue_paid = cur_revenue.fetchone()[0]
        cur_pending = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usd), 0.0) FROM usage_records WHERE billed = 0"
        )
        total_pending = cur_pending.fetchone()[0]
        return {
            "total_priced_skills": total_pricings,
            "total_usage_records": total_usage,
            "total_billing_cycles": total_cycles,
            "total_revenue_paid_usd": total_revenue_paid,
            "total_pending_usd": total_pending,
            "db_path": str(self.db_path),
        }

    def close(self) -> None:
        if self._conn:
            self._conn.close()
