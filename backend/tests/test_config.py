"""
OTC Block Trade Entity Config — Tests
=======================================

Verifies that the OTCBlockTrade entity config correctly wires the
negotiation engine, state machine, and consensus rules.
"""

import pytest

from backend.config import (
    OTC_LIFECYCLE_STAGES,
    OTC_LOCK_RULES,
    OTC_MANDATORY_FIELDS,
    OTC_NEGOTIABLE_FIELDS,
    OTC_TRADE_CONFIG,
    create_otc_consensus_config,
    create_otc_negotiation_stack,
    create_otc_orchestrator,
)
from vellum.negotiation import (
    FieldNegotiationStatus,
    get_entity_config,
)


class TestEntityRegistration:
    """Entity type registration and config integrity."""

    def test_entity_type_registered(self):
        config = get_entity_config("OTCBlockTrade")
        assert config is not None
        assert config.graphql_type == "OTCBlockTrade"

    def test_lifecycle_stages(self):
        assert OTC_LIFECYCLE_STAGES[0] == "INDICATION"
        assert OTC_LIFECYCLE_STAGES[-1] == "FAILED"
        assert "AGREED" in OTC_LIFECYCLE_STAGES
        assert "SETTLING" in OTC_LIFECYCLE_STAGES
        assert "SETTLED" in OTC_LIFECYCLE_STAGES

    def test_all_negotiable_fields_have_lock_rules(self):
        for field in OTC_NEGOTIABLE_FIELDS:
            assert field in OTC_LOCK_RULES, (
                f"Field '{field}' is negotiable but has no lock rule"
            )

    def test_mandatory_fields_are_subset_of_negotiable(self):
        for stage, fields in OTC_MANDATORY_FIELDS.items():
            for field in fields:
                assert field in OTC_NEGOTIABLE_FIELDS, (
                    f"Mandatory field '{field}' at stage '{stage}' "
                    f"is not in OTC_NEGOTIABLE_FIELDS"
                )

    def test_participant_fields(self):
        assert "buyer" in OTC_TRADE_CONFIG.participant_fields
        assert "seller" in OTC_TRADE_CONFIG.participant_fields

    def test_field_type_hints(self):
        hints = OTC_TRADE_CONFIG.field_type_hints
        assert hints["price_per_token"] == "Float"
        assert hints["quantity"] == "Int"
        assert hints["partial_fill_allowed"] == "Boolean"
        assert hints["price_oracle_source"] == "String"
        assert hints["escrow_pct"] == "Float"
        assert hints["max_slippage_bps"] == "Int"

    def test_twelve_negotiable_fields(self):
        assert len(OTC_NEGOTIABLE_FIELDS) == 12


class TestConsensus:
    """Bilateral consensus configuration."""

    def test_bilateral_config(self):
        config = create_otc_consensus_config()
        assert "buyer" in config.party_roles
        assert "seller" in config.party_roles
        assert config.default_authoritative_role == "seller"

    def test_both_parties_required(self):
        config = create_otc_consensus_config()
        assert "buyer" in config.default_required_approvers
        assert "seller" in config.default_required_approvers


class TestNegotiationStack:
    """Wired negotiation stack (engine + FSM + proposal manager)."""

    def test_stack_creation(self):
        engine, fsm, pm = create_otc_negotiation_stack()
        assert engine is not None
        assert fsm is not None
        assert pm is not None

    def test_orchestrator_creation(self):
        orch = create_otc_orchestrator()
        assert orch is not None
        assert orch.entity_type == "OTCBlockTrade"


class TestFieldLocking:
    """Field lock rules via the state machine."""

    def test_price_locked_at_agreed(self):
        _, fsm, _ = create_otc_negotiation_stack()
        assert fsm.is_field_locked("price_per_token", "AGREED")

    def test_price_not_locked_at_negotiation(self):
        _, fsm, _ = create_otc_negotiation_stack()
        assert not fsm.is_field_locked("price_per_token", "NEGOTIATION")

    def test_oracle_locks_early(self):
        _, fsm, _ = create_otc_negotiation_stack()
        assert fsm.is_field_locked("price_oracle_source", "NEGOTIATION")
        assert fsm.is_field_locked("twap_window_mins", "NEGOTIATION")

    def test_escrow_locked_at_agreed(self):
        _, fsm, _ = create_otc_negotiation_stack()
        assert not fsm.is_field_locked("escrow_pct", "NEGOTIATION")
        assert fsm.is_field_locked("escrow_pct", "AGREED")


class TestMandatoryFields:
    """Stage advancement gating."""

    def test_cannot_advance_to_agreed_without_all_fields(self):
        orch = create_otc_orchestrator()
        entity_id = "TEST-001"

        can, blocking = orch.check_can_advance("AGREED", entity_id=entity_id)
        assert not can
        assert len(blocking) > 0

    def test_can_advance_after_all_mandatory_agreed(self):
        orch = create_otc_orchestrator()
        entity_id = "TEST-002"

        for field in OTC_MANDATORY_FIELDS["AGREED"]:
            orch._set_field_status(
                entity_id, field, FieldNegotiationStatus.AGREED
            )

        can, blocking = orch.check_can_advance("AGREED", entity_id=entity_id)
        assert can
        assert len(blocking) == 0


class TestNegotiationFlow:
    """End-to-end negotiation flow through the orchestrator."""

    def test_submit_and_accept_proposal(self):
        orch = create_otc_orchestrator()
        entity_id = "OTC-001"

        # Seller proposes price
        result = orch.submit_proposal(
            entity_id=entity_id,
            field_path="price_per_token",
            proposed_value="1.05",
            proposer_party_id="seller-node",
            proposer_collaborator_id="agent-seller",
            proposer_role="seller",
        )
        assert result.success
        proposal_id = result.proposal.proposal_id

        status = orch.get_field_status(entity_id, "price_per_token")
        assert status == FieldNegotiationStatus.PROPOSED

        # Buyer accepts
        accept = orch.accept_proposal(
            proposal_id=proposal_id,
            acceptor_party_id="buyer-node",
            acceptor_collaborator_id="agent-buyer",
            acceptor_role="buyer",
        )
        assert accept.success
        assert accept.consensus_reached

        status = orch.get_field_status(entity_id, "price_per_token")
        assert status == FieldNegotiationStatus.AGREED

    def test_reject_with_counter(self):
        orch = create_otc_orchestrator()
        entity_id = "OTC-002"

        # Seller proposes settlement window
        result = orch.submit_proposal(
            entity_id=entity_id,
            field_path="settlement_window_secs",
            proposed_value="60",
            proposer_party_id="seller-node",
            proposer_collaborator_id="agent-seller",
            proposer_role="seller",
        )
        assert result.success
        proposal_id = result.proposal.proposal_id

        # Buyer counters with longer window
        reject = orch.reject_proposal(
            proposal_id=proposal_id,
            rejector_party_id="buyer-node",
            rejector_collaborator_id="agent-buyer",
            rejector_role="buyer",
            reason="Need more time for settlement",
            counter_value="300",
        )
        assert reject.success
        assert reject.counter_proposal is not None

        status = orch.get_field_status(entity_id, "settlement_window_secs")
        assert status == FieldNegotiationStatus.COUNTER_PROPOSED

        # Seller accepts the counter
        accept = orch.accept_proposal(
            proposal_id=reject.counter_proposal.proposal_id,
            acceptor_party_id="seller-node",
            acceptor_collaborator_id="agent-seller",
            acceptor_role="seller",
        )
        assert accept.success
        assert accept.consensus_reached

    def test_locked_field_rejects_proposal(self):
        orch = create_otc_orchestrator()
        entity_id = "OTC-003"

        # Try to propose on oracle (locked at NEGOTIATION)
        result = orch.submit_proposal(
            entity_id=entity_id,
            field_path="price_oracle_source",
            proposed_value="uniswap_v3",
            proposer_party_id="seller-node",
            proposer_collaborator_id="agent-seller",
            proposer_role="seller",
            lifecycle_stage="NEGOTIATION",
        )
        assert not result.success
        assert "locked" in result.error.lower()

    def test_full_negotiation_to_agreed(self):
        """Negotiate all 12 fields to AGREED status."""
        orch = create_otc_orchestrator()
        entity_id = "OTC-FULL"

        field_values = {
            "price_per_token": "1.05",
            "quantity": "100000",
            "min_fill_quantity": "50000",
            "partial_fill_allowed": "true",
            "settlement_window_secs": "120",
            "execution_tranches": "1",
            "max_slippage_bps": "50",
            "escrow_pct": "50.0",
            "penalty_bps": "200",
            "expire_after_secs": "600",
            "price_oracle_source": "uniswap_v3",
            "twap_window_mins": "30",
        }

        for field, value in field_values.items():
            result = orch.submit_proposal(
                entity_id=entity_id,
                field_path=field,
                proposed_value=value,
                proposer_party_id="seller-node",
                proposer_collaborator_id="agent-seller",
                proposer_role="seller",
            )
            assert result.success, f"Failed to propose {field}: {result.error}"

            accept = orch.accept_proposal(
                proposal_id=result.proposal.proposal_id,
                acceptor_party_id="buyer-node",
                acceptor_collaborator_id="agent-buyer",
                acceptor_role="buyer",
            )
            assert accept.success, f"Failed to accept {field}: {accept.error}"
            assert accept.consensus_reached, f"No consensus on {field}"

        can, blocking = orch.check_can_advance("AGREED", entity_id=entity_id)
        assert can, f"Cannot advance to AGREED, blocking: {blocking}"
