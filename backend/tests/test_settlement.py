"""
Settlement & ZKP Verification — Tests
=======================================

Tests the full exploit bounty settlement flow:
    1. Fund escrow
    2. Generate ZKP (hacker proves exploit exists)
    3. Verify ZKP on-chain
    4. Release escrow (or return on failure)
"""

import pytest
import pytest_asyncio

from backend.settlement.zkp_verifier import MockZKPVerifier, ExploitProof
from backend.settlement.bridge import MockSettlementBridge


# ── MockZKPVerifier Unit Tests ────────────────────────────────────

class TestProofGeneration:

    @pytest.fixture
    def verifier(self):
        return MockZKPVerifier(verification_delay=0)

    @pytest.mark.asyncio
    async def test_generate_proof_returns_valid_structure(self, verifier):
        proof = await verifier.generate_proof(
            target_contract="0xDEFI_PROTOCOL_123",
            exploit_details="reentrancy in withdraw() function",
            severity_claim=9.1,
            drain_amount_claim=2_500_000.0,
            prover_id="anon-hacker-42",
        )
        assert proof.proof_id.startswith("ZKP-")
        assert proof.target_contract == "0xDEFI_PROTOCOL_123"
        assert proof.severity_claim == 9.1
        assert proof.drain_amount_claim == 2_500_000.0
        assert proof.prover == "anon-hacker-42"
        assert len(proof.exploit_commitment) == 64  # SHA-256 hex
        assert len(proof.proof_bytes) == 64

    @pytest.mark.asyncio
    async def test_exploit_commitment_hides_details(self, verifier):
        """Commitment should be a hash — not the raw exploit details."""
        proof = await verifier.generate_proof(
            target_contract="0xTARGET",
            exploit_details="the secret sauce",
            severity_claim=7.0,
            drain_amount_claim=100_000.0,
            prover_id="hacker",
        )
        assert "secret" not in proof.exploit_commitment
        assert "sauce" not in proof.exploit_commitment

    @pytest.mark.asyncio
    async def test_different_exploits_different_commitments(self, verifier):
        p1 = await verifier.generate_proof(
            target_contract="0xA", exploit_details="exploit A",
            severity_claim=5.0, drain_amount_claim=100.0, prover_id="h",
        )
        p2 = await verifier.generate_proof(
            target_contract="0xA", exploit_details="exploit B",
            severity_claim=5.0, drain_amount_claim=100.0, prover_id="h",
        )
        assert p1.exploit_commitment != p2.exploit_commitment


class TestProofVerification:

    @pytest.fixture
    def verifier(self):
        return MockZKPVerifier(verification_delay=0)

    @pytest.mark.asyncio
    async def test_valid_proof_verifies(self, verifier):
        proof = await verifier.generate_proof(
            target_contract="0xVULN_CONTRACT",
            exploit_details="integer overflow in mint()",
            severity_claim=8.5,
            drain_amount_claim=1_000_000.0,
            prover_id="whitehat",
        )
        result = await verifier.verify_proof(proof)
        assert result.valid
        assert result.severity_verified
        assert result.drain_amount_verified
        assert result.gas_used == 287_000
        assert result.verification_id.startswith("VERIFY-")

    @pytest.mark.asyncio
    async def test_tampered_proof_fails(self, verifier):
        proof = await verifier.generate_proof(
            target_contract="0xTARGET",
            exploit_details="the real exploit",
            severity_claim=9.0,
            drain_amount_claim=500_000.0,
            prover_id="hacker",
        )
        # Tamper with proof bytes
        proof.proof_bytes = "0" * 64
        result = await verifier.verify_proof(proof)
        assert not result.valid

    @pytest.mark.asyncio
    async def test_invalid_severity_fails(self, verifier):
        proof = await verifier.generate_proof(
            target_contract="0xTARGET",
            exploit_details="exploit",
            severity_claim=15.0,  # Invalid: CVSS max is 10.0
            drain_amount_claim=100.0,
            prover_id="hacker",
        )
        # Proof bytes will match (mock generates them), but severity check fails
        result = await verifier.verify_proof(proof)
        assert not result.valid
        assert not result.severity_verified

    @pytest.mark.asyncio
    async def test_zero_drain_amount_fails(self, verifier):
        proof = await verifier.generate_proof(
            target_contract="0xTARGET",
            exploit_details="exploit",
            severity_claim=5.0,
            drain_amount_claim=0.0,  # Invalid: must be > 0
            prover_id="hacker",
        )
        result = await verifier.verify_proof(proof)
        assert not result.valid
        assert not result.drain_amount_verified


class TestEscrow:

    @pytest.fixture
    def verifier(self):
        return MockZKPVerifier(verification_delay=0)

    @pytest.mark.asyncio
    async def test_fund_escrow(self, verifier):
        escrow = await verifier.fund_escrow("BOUNTY-001", 100_000.0, 50.0)
        assert escrow.status == "FUNDED"
        assert escrow.escrow_amount == 50_000.0  # 50% of 100k
        assert escrow.funding_tx_hash.startswith("0x")

    @pytest.mark.asyncio
    async def test_release_escrow_on_valid_proof(self, verifier):
        # Fund first
        await verifier.fund_escrow("BOUNTY-002", 200_000.0, 75.0)

        # Generate + verify proof
        proof = await verifier.generate_proof(
            target_contract="0xTARGET",
            exploit_details="real exploit",
            severity_claim=9.0,
            drain_amount_claim=1_000_000.0,
            prover_id="hacker",
        )
        verification = await verifier.verify_proof(proof)
        assert verification.valid

        # Release
        escrow = await verifier.release_escrow("BOUNTY-002", verification)
        assert escrow.status == "RELEASED"
        assert escrow.release_tx_hash.startswith("0x")

    @pytest.mark.asyncio
    async def test_return_escrow_on_invalid_proof(self, verifier):
        await verifier.fund_escrow("BOUNTY-003", 100_000.0, 50.0)

        # Generate proof then tamper
        proof = await verifier.generate_proof(
            target_contract="0xTARGET",
            exploit_details="real exploit",
            severity_claim=9.0,
            drain_amount_claim=1_000_000.0,
            prover_id="hacker",
        )
        proof.proof_bytes = "TAMPERED" + proof.proof_bytes[8:]
        verification = await verifier.verify_proof(proof)
        assert not verification.valid

        # Escrow should be returned
        escrow = await verifier.release_escrow("BOUNTY-003", verification)
        assert escrow.status == "RETURNED"


# ── OTC Settlement Flow (API Integration) ─────────────────────────

class TestSettlementAPI:
    """End-to-end OTC settlement flow through the API."""

    @pytest_asyncio.fixture
    async def client(self):
        from httpx import AsyncClient, ASGITransport
        from backend.app import create_app
        from backend.config import create_otc_orchestrator

        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            app.state.orchestrator = create_otc_orchestrator()
            app.state.trade_store = {}
            app.state.settlement_bridge = MockSettlementBridge(settlement_delay=0)
            app.state.mpp_mode = "mock"
            yield c

    async def _create_trade(self, client) -> str:
        r = await client.post("/api/trades", json={
            "seller_id": "seller-node",
            "buyer_id": "buyer-node",
            "price_per_token": 1.05,
            "quantity": 100000,
        })
        return r.json()["id"]

    @pytest.mark.asyncio
    async def test_full_otc_settlement_flow(self, client):
        """Negotiate → escrow → submit → settled."""
        trade_id = await self._create_trade(client)

        # Step 1: Fund escrow
        r = await client.post(f"/api/settlement/escrow/{trade_id}", json={
            "trade_notional": 105000.0,
            "escrow_pct": 50.0,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"]
        assert data["escrow_amount"] == 52500.0
        assert data["mpp_mode"] == "mock"

        # Trade should be SETTLING
        r = await client.get(f"/api/trades/{trade_id}")
        assert r.json()["status"] == "SETTLING"

        # Step 2: Negotiate all fields to AGREED via orchestrator
        orch = client._transport.app.state.orchestrator  # type: ignore
        from backend.config import OTC_MANDATORY_FIELDS
        from vellum.negotiation import FieldNegotiationStatus
        for field in OTC_MANDATORY_FIELDS["AGREED"]:
            result = orch.submit_proposal(
                entity_id=trade_id, field_path=field,
                proposed_value="1.05" if field == "price_per_token" else "100",
                proposer_party_id="seller-node",
                proposer_collaborator_id="agent-seller",
                proposer_role="seller",
            )
            orch.accept_proposal(
                proposal_id=result.proposal.proposal_id,
                acceptor_party_id="buyer-node",
                acceptor_collaborator_id="agent-buyer",
                acceptor_role="buyer",
            )

        # Step 3: Submit settlement (hashes agreed terms + atomic swap)
        r = await client.post(f"/api/settlement/submit/{trade_id}")
        assert r.status_code == 200
        settle_data = r.json()
        assert settle_data["success"]
        assert settle_data["tx_hash"].startswith("0x")
        assert settle_data["content_hash"]  # SHA-256 of agreed terms

        # Trade should be SETTLED
        r = await client.get(f"/api/trades/{trade_id}")
        assert r.json()["status"] == "SETTLED"

    @pytest.mark.asyncio
    async def test_settlement_status(self, client):
        trade_id = await self._create_trade(client)

        # Before settlement
        r = await client.get(f"/api/settlement/status/{trade_id}")
        assert r.status_code == 200
        assert r.json()["trade_status"] == "INDICATION"
        assert r.json()["mpp_mode"] == "mock"

        # After funding escrow
        await client.post(f"/api/settlement/escrow/{trade_id}", json={
            "trade_notional": 105000.0,
            "escrow_pct": 100.0,
        })
        r = await client.get(f"/api/settlement/status/{trade_id}")
        assert r.json()["trade_status"] == "SETTLING"

    @pytest.mark.asyncio
    async def test_submit_without_agreement_fails(self, client):
        """Cannot submit settlement if negotiation isn't complete."""
        trade_id = await self._create_trade(client)

        r = await client.post(f"/api/settlement/submit/{trade_id}")
        assert r.status_code == 400
        assert "no agreed values" in r.json()["detail"].lower()
