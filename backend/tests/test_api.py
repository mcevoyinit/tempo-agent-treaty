"""
API Integration Tests
======================

Tests the FastAPI routes end-to-end using httpx TestClient.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from backend.app import create_app


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        from backend.config import create_otc_orchestrator
        app.state.orchestrator = create_otc_orchestrator()
        app.state.trade_store = {}
        yield c


@pytest.mark.asyncio
async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_create_and_list_trades(client):
    r = await client.post("/api/trades", json={
        "seller_id": "seller-node",
        "buyer_id": "buyer-node",
        "price_per_token": 1.05,
        "quantity": 100000,
    })
    assert r.status_code == 200
    trade = r.json()
    assert trade["price_per_token"] == 1.05
    assert trade["quantity"] == 100000
    assert trade["status"] == "INDICATION"
    trade_id = trade["id"]

    r = await client.get("/api/trades")
    assert r.status_code == 200
    trades = r.json()["trades"]
    assert len(trades) == 1
    assert trades[0]["id"] == trade_id

    r = await client.get(f"/api/trades/{trade_id}")
    assert r.status_code == 200
    assert r.json()["id"] == trade_id


@pytest.mark.asyncio
async def test_negotiation_flow(client):
    r = await client.post("/api/trades", json={
        "seller_id": "seller-node",
        "buyer_id": "buyer-node",
    })
    trade_id = r.json()["id"]

    # Submit proposal
    r = await client.post("/api/negotiation/proposals", json={
        "entity_id": trade_id,
        "field_path": "price_per_token",
        "proposed_value": "1.05",
        "proposer_party_id": "seller-node",
        "proposer_collaborator_id": "agent-seller",
        "proposer_role": "seller",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["success"]
    proposal_id = data["proposal_id"]

    # Check field status
    r = await client.get(f"/api/negotiation/entity/{trade_id}/status")
    assert r.status_code == 200
    statuses = r.json()["field_statuses"]
    assert statuses["price_per_token"] == "PROPOSED"

    # Accept proposal
    r = await client.post(f"/api/negotiation/proposals/{proposal_id}/accept", json={
        "acceptor_party_id": "buyer-node",
        "acceptor_collaborator_id": "agent-buyer",
        "acceptor_role": "buyer",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["success"]
    assert data["consensus_reached"]

    r = await client.get(f"/api/negotiation/entity/{trade_id}/status")
    statuses = r.json()["field_statuses"]
    assert statuses["price_per_token"] == "AGREED"


@pytest.mark.asyncio
async def test_reject_with_counter(client):
    r = await client.post("/api/trades", json={
        "seller_id": "seller-node",
        "buyer_id": "buyer-node",
    })
    trade_id = r.json()["id"]

    r = await client.post("/api/negotiation/proposals", json={
        "entity_id": trade_id,
        "field_path": "settlement_window_secs",
        "proposed_value": "60",
        "proposer_party_id": "seller-node",
        "proposer_collaborator_id": "agent-seller",
        "proposer_role": "seller",
    })
    proposal_id = r.json()["proposal_id"]

    r = await client.post(f"/api/negotiation/proposals/{proposal_id}/reject", json={
        "rejector_party_id": "buyer-node",
        "rejector_collaborator_id": "agent-buyer",
        "rejector_role": "buyer",
        "reason": "Need more time",
        "counter_value": "300",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["counter_proposal_id"] is not None

    r = await client.get(f"/api/negotiation/entity/{trade_id}/status")
    statuses = r.json()["field_statuses"]
    assert statuses["settlement_window_secs"] == "COUNTER_PROPOSED"


@pytest.mark.asyncio
async def test_can_advance_check(client):
    r = await client.post("/api/trades", json={
        "seller_id": "seller-node",
        "buyer_id": "buyer-node",
    })
    trade_id = r.json()["id"]

    r = await client.get(f"/api/negotiation/entity/{trade_id}/can-advance/AGREED")
    assert r.status_code == 200
    data = r.json()
    assert not data["can_advance"]
    assert len(data["blocking_fields"]) > 0


@pytest.mark.asyncio
async def test_locked_field_rejected(client):
    r = await client.post("/api/trades", json={
        "seller_id": "seller-node",
        "buyer_id": "buyer-node",
    })
    trade_id = r.json()["id"]

    # Oracle locks at NEGOTIATION
    r = await client.post("/api/negotiation/proposals", json={
        "entity_id": trade_id,
        "field_path": "price_oracle_source",
        "proposed_value": "uniswap_v3",
        "proposer_party_id": "seller-node",
        "proposer_collaborator_id": "agent-seller",
        "proposer_role": "seller",
        "lifecycle_stage": "NEGOTIATION",
    })
    assert r.status_code == 400
    assert "locked" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_market_data_endpoint(client):
    # Need to init the oracle
    from backend.agent.market_data import MockDEXOracle
    from decimal import Decimal
    client._transport.app.state.dex_oracle = MockDEXOracle(  # type: ignore
        base_price=Decimal("1.00"),
        liquidity_depth=Decimal("500000"),
    )

    r = await client.get("/api/agent/market", params={"quantity": 100000})
    assert r.status_code == 200
    data = r.json()
    assert data["dex_mid_price"] == "1.00"
    assert data["dex_slippage_bps"] > 0
    assert data["block_quantity"] == 100000
    # Seller gets less, buyer pays more
    assert Decimal(data["seller_effective_dex_price"]) < Decimal("1.00")
    assert Decimal(data["buyer_effective_dex_price"]) > Decimal("1.00")
