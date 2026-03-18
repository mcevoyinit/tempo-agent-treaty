"""
Trade CRUD Routes
==================

Simple in-memory trade store for the demo.
No database — trades live in app.state.trade_store.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


class CreateTradeRequest(BaseModel):
    seller_id: str
    buyer_id: str
    token_pair: str = "TEMPO/USDC"
    price_per_token: Optional[float] = None
    quantity: Optional[int] = None


class UpdateTradeFieldRequest(BaseModel):
    field_path: str
    value: Any


def create_trades_router() -> APIRouter:
    router = APIRouter()

    def _store(request: Request) -> dict[str, dict[str, Any]]:
        return request.app.state.trade_store

    @router.get("")
    async def list_trades(request: Request):
        store = _store(request)
        return {"trades": list(store.values())}

    @router.get("/{trade_id}")
    async def get_trade(trade_id: str, request: Request):
        store = _store(request)
        trade = store.get(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
        return trade

    @router.post("")
    async def create_trade(body: CreateTradeRequest, request: Request):
        store = _store(request)
        trade_id = f"OTC-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(tz=timezone.utc).isoformat()

        trade = {
            "id": trade_id,
            "status": "INDICATION",
            "token_pair": body.token_pair,
            "created_at": now,
            "updated_at": now,
            # Economics
            "price_per_token": body.price_per_token,
            "quantity": body.quantity,
            "min_fill_quantity": None,
            # Execution
            "partial_fill_allowed": None,
            "settlement_window_secs": None,
            "execution_tranches": None,
            "max_slippage_bps": None,
            # Trust
            "escrow_pct": None,
            "penalty_bps": None,
            "expire_after_secs": None,
            # Market Reference
            "price_oracle_source": None,
            "twap_window_mins": None,
            # Parties
            "seller_id": body.seller_id,
            "buyer_id": body.buyer_id,
            # Settlement
            "settlement_tx_hash": None,
            "content_hash": None,
        }

        store[trade_id] = trade
        return trade

    @router.patch("/{trade_id}")
    async def update_trade_field(
        trade_id: str, body: UpdateTradeFieldRequest, request: Request
    ):
        store = _store(request)
        trade = store.get(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        trade[body.field_path] = body.value
        trade["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        return trade

    @router.patch("/{trade_id}/status")
    async def update_trade_status(
        trade_id: str, request: Request, status: str = ""
    ):
        store = _store(request)
        trade = store.get(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")

        trade["status"] = status
        trade["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
        return trade

    return router
