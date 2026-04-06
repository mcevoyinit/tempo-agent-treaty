"""
Settlement Routes
==================

REST endpoints for OTC block trade settlement:
    1. POST /escrow/{trade_id}    — Fund escrow (MPP session or mock)
    2. POST /submit/{trade_id}    — Hash agreed terms + settle via MPP
    3. GET  /status/{trade_id}    — Settlement status
"""

import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


class FundEscrowRequest(BaseModel):
    trade_notional: float
    escrow_pct: float


def create_settlement_router() -> APIRouter:
    router = APIRouter()

    def _bridge(request: Request):
        return request.app.state.settlement_bridge

    # ── Step 1: Fund Escrow ──────────────────────────────────────

    @router.post("/escrow/{trade_id}")
    async def fund_escrow(trade_id: str, body: FundEscrowRequest, request: Request):
        """Fund escrow for a trade. In MPP mode, opens a payment session."""
        trade_store = request.app.state.trade_store
        trade = trade_store.get(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        trade["status"] = "SETTLING"
        return {
            "success": True,
            "trade_id": trade_id,
            "escrow_amount": body.trade_notional * (body.escrow_pct / 100.0),
            "escrow_pct": body.escrow_pct,
            "mpp_mode": request.app.state.mpp_mode,
        }

    # ── Step 2: Submit Settlement ─────────────────────────────────

    @router.post("/submit/{trade_id}")
    async def submit_settlement(trade_id: str, request: Request):
        """Hash agreed terms + settle via MPP (or mock)."""
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

        # Build explorer URL if available
        explorer_url = None
        if result.tx_hash and hasattr(bridge, "explorer_url"):
            explorer_url = bridge.explorer_url(result.tx_hash)

        return {
            "success": result.success,
            "settlement_id": result.settlement_id,
            "tx_hash": result.tx_hash,
            "content_hash": result.content_hash,
            "canonical_form": result.canonical_form,
            "explorer_url": explorer_url,
            "mpp_mode": request.app.state.mpp_mode,
            "error": result.error,
        }

    # ── Status ───────────────────────────────────────────────────

    @router.get("/status/{trade_id}")
    async def settlement_status(trade_id: str, request: Request):
        """Settlement status including MPP receipt details."""
        trade_store = request.app.state.trade_store
        trade = trade_store.get(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        return {
            "trade_id": trade_id,
            "trade_status": trade.get("status"),
            "content_hash": trade.get("content_hash"),
            "settlement_tx_hash": trade.get("settlement_tx_hash"),
            "mpp_mode": request.app.state.mpp_mode,
        }

    return router
