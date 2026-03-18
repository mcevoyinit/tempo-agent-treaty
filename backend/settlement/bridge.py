"""
Settlement Bridge
==================

Bridges agreed OTC trades to on-chain settlement.
Uses Vellum's SHA256Hasher to create content hashes proving
off-chain negotiation matches on-chain record.

MockSettlementBridge for demo; TempoSettlementBridge for production.
"""

import uuid
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from vellum.sealing.hasher import SHA256Hasher


@dataclass
class SettlementResult:
    success: bool
    settlement_id: str
    tx_hash: Optional[str] = None
    content_hash: Optional[str] = None
    canonical_form: Optional[str] = None
    error: Optional[str] = None
    submitted_at: Optional[str] = None
    confirmed_at: Optional[str] = None


class SettlementBridge(Protocol):
    """Protocol for settlement bridges."""

    async def submit_settlement(
        self, trade_id: str, agreed_values: dict[str, Any]
    ) -> SettlementResult: ...

    async def check_status(self, settlement_id: str) -> SettlementResult: ...


class MockSettlementBridge:
    """
    Simulates Tempo settlement with configurable delays.

    Steps:
        1. Compute content hash of agreed terms (SHA-256)
        2. Simulate escrow lock (delay)
        3. Simulate atomic swap execution (delay)
        4. Return mock tx_hash
    """

    def __init__(
        self,
        settlement_delay: float = 2.0,
        failure_rate: float = 0.0,
    ):
        self.hasher = SHA256Hasher()
        self.settlement_delay = settlement_delay
        self.failure_rate = failure_rate
        self._settlements: dict[str, SettlementResult] = {}

    async def submit_settlement(
        self, trade_id: str, agreed_values: dict[str, Any]
    ) -> SettlementResult:
        """Submit trade for simulated settlement."""
        settlement_id = f"SETTLE-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(tz=timezone.utc).isoformat()

        # Compute content hash of the agreed trade terms
        content_hash_result = self.hasher.compute_hash(agreed_values)

        # Simulate settlement delay
        await asyncio.sleep(self.settlement_delay)

        # Check for simulated failure
        import random
        if random.random() < self.failure_rate:
            result = SettlementResult(
                success=False,
                settlement_id=settlement_id,
                content_hash=content_hash_result.digest,
                canonical_form=content_hash_result.canonical_form,
                error="Simulated settlement failure (insufficient escrow)",
                submitted_at=now,
            )
            self._settlements[settlement_id] = result
            return result

        # Success
        tx_hash = f"0x{uuid.uuid4().hex}"
        confirmed_at = datetime.now(tz=timezone.utc).isoformat()

        result = SettlementResult(
            success=True,
            settlement_id=settlement_id,
            tx_hash=tx_hash,
            content_hash=content_hash_result.digest,
            canonical_form=content_hash_result.canonical_form,
            submitted_at=now,
            confirmed_at=confirmed_at,
        )
        self._settlements[settlement_id] = result
        return result

    async def check_status(self, settlement_id: str) -> SettlementResult:
        result = self._settlements.get(settlement_id)
        if not result:
            return SettlementResult(
                success=False,
                settlement_id=settlement_id,
                error=f"Settlement {settlement_id} not found",
            )
        return result
