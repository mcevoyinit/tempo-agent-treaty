"""
Settlement Routes
==================

REST endpoints for OTC block trade settlement:
    1. POST /escrow/{trade_id}    — Fund escrow on-chain
    2. POST /submit/{trade_id}    — Hash agreed terms + atomic swap
    3. GET  /status/{trade_id}    — Settlement status
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.settlement.bridge import MockSettlementBridge
from backend.settlement.zkp_verifier import MockZKPVerifier


class FundEscrowRequest(BaseModel):
    trade_notional: float
    escrow_pct: float


def create_settlement_router() -> APIRouter:
    router = APIRouter()

    def _bridge(request: Request) -> MockSettlementBridge:
        if not hasattr(request.app.state, "settlement_bridge"):
            request.app.state.settlement_bridge = MockSettlementBridge(
                settlement_delay=0.5,
            )
        return request.app.state.settlement_bridge

    def _zkp(request: Request) -> MockZKPVerifier:
        if not hasattr(request.app.state, "zkp_verifier"):
            request.app.state.zkp_verifier = MockZKPVerifier(
                verification_delay=0.3,
            )
        return request.app.state.zkp_verifier

    # ── Step 1: Fund Escrow ──────────────────────────────────────

    @router.post("/escrow/{trade_id}")
    async def fund_escrow(trade_id: str, body: FundEscrowRequest, request: Request):
        """Both parties fund escrow on-chain. Moves trade to SETTLING."""
        trade_store = request.app.state.trade_store
        trade = trade_store.get(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        zkp = _zkp(request)
        escrow = await zkp.fund_escrow(trade_id, body.trade_notional, body.escrow_pct)

        trade["status"] = "SETTLING"
        return {
            "success": True,
            "trade_id": trade_id,
            "escrow_amount": escrow.escrow_amount,
            "escrow_pct": escrow.escrow_pct,
            "funding_tx_hash": escrow.funding_tx_hash,
            "funded_at": escrow.funded_at,
        }

    # ── Step 2: Submit Settlement ─────────────────────────────────

    @router.post("/submit/{trade_id}")
    async def submit_settlement(trade_id: str, request: Request):
        """Hash agreed terms + execute atomic swap on Tempo."""
        bridge = _bridge(request)
        trade_store = request.app.state.trade_store
        orch = request.app.state.orchestrator

        trade = trade_store.get(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        agreed_values = orch._agreed_values.get(trade_id, {})
        if not agreed_values:
            raise HTTPException(
                status_code=400,
                detail="No agreed values — negotiation not complete",
            )

        result = await bridge.submit_settlement(trade_id, agreed_values)

        if result.success:
            trade["status"] = "SETTLED"
            trade["settlement_tx_hash"] = result.tx_hash
            trade["content_hash"] = result.content_hash
        else:
            trade["status"] = "FAILED"

        return {
            "success": result.success,
            "settlement_id": result.settlement_id,
            "tx_hash": result.tx_hash,
            "content_hash": result.content_hash,
            "canonical_form": result.canonical_form,
            "error": result.error,
        }

    # ── Status ───────────────────────────────────────────────────

    @router.get("/status/{trade_id}")
    async def settlement_status(trade_id: str, request: Request):
        """Settlement status: escrow + content hash + tx."""
        trade_store = request.app.state.trade_store
        trade = trade_store.get(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        zkp = _zkp(request)
        escrow = zkp.get_escrow(trade_id)

        return {
            "trade_id": trade_id,
            "trade_status": trade.get("status"),
            "escrow": {
                "status": escrow.status if escrow else "NOT_FUNDED",
                "amount": escrow.escrow_amount if escrow else 0,
                "funding_tx": escrow.funding_tx_hash if escrow else None,
            },
            "content_hash": trade.get("content_hash"),
            "settlement_tx_hash": trade.get("settlement_tx_hash"),
        }

    return router
