"""
Agent Control Routes
=====================

REST endpoints for controlling the agent:
    GET  /status           → agent state + recent decisions
    POST /config           → update PolicyConfig live
    POST /pause            → pause agent loop
    POST /resume           → resume agent loop
    POST /simulate         → run a full dual-agent negotiation
    POST /mode             → switch agent mode (auto/supervised/manual)
    GET  /market            → current DEX market snapshot + BATNA
"""

from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.agent.types import AgentMode, AgentState, PolicyConfig, PolicyDecision
from backend.agent.agent_loop import DualAgentSimulator
from backend.agent.market_data import MockDEXOracle
from backend.config import create_otc_orchestrator


class UpdatePolicyRequest(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_quantity: Optional[int] = None
    max_quantity: Optional[int] = None
    min_settlement_secs: Optional[int] = None
    max_settlement_secs: Optional[int] = None
    min_slippage_bps: Optional[int] = None
    max_slippage_bps: Optional[int] = None
    min_escrow_pct: Optional[float] = None
    max_escrow_pct: Optional[float] = None
    min_penalty_bps: Optional[int] = None
    max_penalty_bps: Optional[int] = None


class SetModeRequest(BaseModel):
    mode: str  # "FULL_AUTO", "SUPERVISED", "MANUAL"


class SimulateRequest(BaseModel):
    entity_id: Optional[str] = None
    seller_values: dict[str, Any]


def create_agent_router() -> APIRouter:
    router = APIRouter()

    def _get_simulator(request: Request) -> DualAgentSimulator:
        if not hasattr(request.app.state, "simulator"):
            request.app.state.simulator = DualAgentSimulator(
                orchestrator=request.app.state.orchestrator,
            )
        return request.app.state.simulator

    def _get_oracle(request: Request) -> MockDEXOracle:
        if not hasattr(request.app.state, "dex_oracle"):
            request.app.state.dex_oracle = MockDEXOracle(
                base_price=Decimal("1.00"),
                liquidity_depth=Decimal("500000"),
            )
        return request.app.state.dex_oracle

    @router.get("/status")
    async def agent_status(request: Request):
        sim = _get_simulator(request)
        return {
            "seller": _serialize_agent_state(sim.seller.state),
            "buyer": _serialize_agent_state(sim.buyer.state),
        }

    @router.get("/market")
    async def market_data(request: Request, quantity: int = 100000):
        """Get current DEX market snapshot and BATNA for a given block size."""
        oracle = _get_oracle(request)
        snapshot = oracle.get_snapshot(quantity)
        seller_effective = oracle.compute_effective_dex_price(quantity, "sell")
        buyer_effective = oracle.compute_effective_dex_price(quantity, "buy")

        return {
            "dex_mid_price": str(snapshot.dex_mid_price),
            "dex_slippage_bps": snapshot.dex_slippage_bps,
            "liquidity_depth": str(snapshot.liquidity_depth_quote),
            "spread_bps": snapshot.spread_bps,
            "seller_effective_dex_price": str(seller_effective),
            "buyer_effective_dex_price": str(buyer_effective),
            "block_quantity": quantity,
            "timestamp": snapshot.timestamp,
        }

    @router.post("/config")
    async def update_config(body: UpdatePolicyRequest, request: Request):
        sim = _get_simulator(request)
        for agent in [sim.seller, sim.buyer]:
            policy = agent.state.policy
            if body.min_price is not None:
                policy.min_price = Decimal(str(body.min_price))
            if body.max_price is not None:
                policy.max_price = Decimal(str(body.max_price))
            if body.min_quantity is not None:
                policy.min_quantity = body.min_quantity
            if body.max_quantity is not None:
                policy.max_quantity = body.max_quantity
            if body.min_settlement_secs is not None:
                policy.min_settlement_secs = body.min_settlement_secs
            if body.max_settlement_secs is not None:
                policy.max_settlement_secs = body.max_settlement_secs
            if body.min_slippage_bps is not None:
                policy.min_slippage_bps = body.min_slippage_bps
            if body.max_slippage_bps is not None:
                policy.max_slippage_bps = body.max_slippage_bps
            if body.min_escrow_pct is not None:
                policy.min_escrow_pct = Decimal(str(body.min_escrow_pct))
            if body.max_escrow_pct is not None:
                policy.max_escrow_pct = Decimal(str(body.max_escrow_pct))
            if body.min_penalty_bps is not None:
                policy.min_penalty_bps = body.min_penalty_bps
            if body.max_penalty_bps is not None:
                policy.max_penalty_bps = body.max_penalty_bps
            agent.policy_engine = __import__(
                "backend.agent.policy_engine", fromlist=["PolicyEngine"]
            ).PolicyEngine(policy)

        return {"success": True, "message": "Policy updated for both agents"}

    @router.post("/pause")
    async def pause_agent(request: Request):
        sim = _get_simulator(request)
        sim.seller.state.paused = True
        sim.buyer.state.paused = True
        return {"success": True, "paused": True}

    @router.post("/resume")
    async def resume_agent(request: Request):
        sim = _get_simulator(request)
        sim.seller.state.paused = False
        sim.buyer.state.paused = False
        return {"success": True, "paused": False}

    @router.post("/mode")
    async def set_mode(body: SetModeRequest, request: Request):
        sim = _get_simulator(request)
        mode = AgentMode(body.mode)
        sim.seller.state.mode = mode
        sim.buyer.state.mode = mode
        return {"success": True, "mode": mode.value}

    @router.post("/simulate")
    async def simulate_negotiation(body: SimulateRequest, request: Request):
        """Run a full dual-agent negotiation and return the decision log + savings."""
        oracle = _get_oracle(request)

        import uuid
        entity_id = body.entity_id or f"SIM-{uuid.uuid4().hex[:8].upper()}"

        # Fresh orchestrator per simulation (clean state)
        orchestrator = create_otc_orchestrator()

        # Buyer has a TIGHT realistic policy — creates negotiation drama
        # Note: prices outside 1.2x max_price trigger COUNTER (not REFER_TO_LLM)
        buyer_policy = PolicyConfig(
            min_price=Decimal("0.50"),
            max_price=Decimal("0.98"),      # Seller asks 1.05 → ambiguous zone → auto-counter midpoint
            min_quantity=10000,
            max_quantity=500000,
            min_fill_pct=Decimal("25.0"),
            min_settlement_secs=30,
            max_settlement_secs=90,          # Seller asks 120s → COUNTER to 90
            max_tranches=3,
            min_slippage_bps=10,
            max_slippage_bps=80,             # 50 is fine
            min_escrow_pct=Decimal("5.0"),
            max_escrow_pct=Decimal("30.0"),  # Seller asks 50% → COUNTER to 30%
            min_penalty_bps=10,
            max_penalty_bps=120,             # Seller asks 200 → COUNTER to 120
            min_expire_secs=60,
            max_expire_secs=1800,
            min_twap_mins=5,
            max_twap_mins=20,                # Seller asks 30 → COUNTER to 20
            approved_oracles={"uniswap_v3", "chainlink"},
        )

        # Seller has broader limits (will accept buyer's counters mostly)
        seller_policy = PolicyConfig(
            min_price=Decimal("0.95"),       # Won't go below 0.95
            max_price=Decimal("2.00"),
            min_quantity=10000,
            max_quantity=1000000,
            min_fill_pct=Decimal("10.0"),
            min_settlement_secs=10,
            max_settlement_secs=300,
            max_tranches=5,
            min_slippage_bps=5,
            max_slippage_bps=500,
            min_escrow_pct=Decimal("5.0"),
            max_escrow_pct=Decimal("100.0"),
            min_penalty_bps=10,
            max_penalty_bps=500,
            min_expire_secs=30,
            max_expire_secs=3600,
            min_twap_mins=1,
            max_twap_mins=60,
            approved_oracles={"uniswap_v3", "chainlink", "twap_custom"},
        )

        sim = DualAgentSimulator(
            orchestrator=orchestrator,
            seller_config=seller_policy,
            buyer_config=buyer_policy,
        )

        # Create the trade in the store
        trade_store = request.app.state.trade_store
        from datetime import datetime, timezone
        now = datetime.now(tz=timezone.utc).isoformat()
        trade_store[entity_id] = {
            "id": entity_id,
            "status": "NEGOTIATION",
            "created_at": now,
            "updated_at": now,
            **body.seller_values,
            "seller_id": sim.seller.state.party_id,
            "buyer_id": sim.buyer.state.party_id,
        }

        actions = sim.run_negotiation(
            entity_id=entity_id,
            seller_initial_values=body.seller_values,
        )

        # Get final field statuses
        statuses = sim.orchestrator.get_all_field_statuses(entity_id)

        # Compute savings vs DEX
        agreed_values = sim.orchestrator._agreed_values.get(entity_id, {})
        savings_info = None
        if "price_per_token" in agreed_values and "quantity" in agreed_values:
            otc_price = Decimal(str(agreed_values["price_per_token"]))
            qty = int(agreed_values["quantity"])
            seller_savings = oracle.compute_savings(otc_price, qty, "sell")
            buyer_savings = oracle.compute_savings(otc_price, qty, "buy")
            snapshot = oracle.get_snapshot(qty)
            savings_info = {
                "dex_mid_price": str(snapshot.dex_mid_price),
                "dex_slippage_bps": snapshot.dex_slippage_bps,
                "otc_price": str(otc_price),
                "quantity": qty,
                "seller_savings": str(seller_savings),
                "buyer_savings": str(buyer_savings),
            }

        # Tag actions with agent role (first 12 = seller init, rest alternate)
        seller_log = sim.seller.state.decisions_log
        buyer_log = sim.buyer.state.decisions_log
        seller_set = {id(a) for a in seller_log}

        return {
            "entity_id": entity_id,
            "total_actions": len(actions),
            "actions": [
                {
                    "agent": "seller" if id(a) in seller_set else "buyer",
                    "decision": a.decision.value,
                    "field_path": a.field_path,
                    "original_value": a.original_value,
                    "counter_value": a.counter_value,
                    "reasoning": a.reasoning,
                    "confidence": a.confidence,
                }
                for a in actions
            ],
            "field_statuses": {
                path: status.value for path, status in statuses.items()
            },
            "savings_vs_dex": savings_info,
        }

    return router


def _serialize_agent_state(state: AgentState) -> dict:
    return {
        "agent_id": state.agent_id,
        "role": state.role,
        "party_id": state.party_id,
        "mode": state.mode.value,
        "paused": state.paused,
        "total_decisions": state.total_decisions,
        "recent_decisions": [
            {
                "decision": a.decision.value,
                "field_path": a.field_path,
                "reasoning": a.reasoning,
            }
            for a in state.decisions_log[-10:]
        ],
    }
