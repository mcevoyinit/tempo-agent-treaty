"""
Agent Policy Engine & Negotiation Loop — Tests
================================================

Tests the deterministic policy engine, cross-field concession logic,
market data oracle, and the dual-agent simulator.
"""

import pytest
from decimal import Decimal

from backend.config import create_otc_orchestrator
from backend.agent.types import (
    AgentMode,
    AgentState,
    PolicyConfig,
    PolicyDecision,
)
from backend.agent.policy_engine import PolicyEngine
from backend.agent.agent_loop import AgentNegotiator, DualAgentSimulator
from backend.agent.market_data import MockDEXOracle
from vellum.negotiation import FieldNegotiationStatus


# ── PolicyEngine Tests ───────────────────────────────────────────

class TestPriceEvaluation:

    @pytest.fixture
    def engine(self):
        return PolicyEngine(PolicyConfig(
            min_price=Decimal("0.50"),
            max_price=Decimal("2.00"),
        ))

    def test_accept_within_limits(self, engine):
        action = engine.evaluate_proposal("price_per_token", "1.05")
        assert action.decision == PolicyDecision.ACCEPT

    def test_counter_below_min(self, engine):
        action = engine.evaluate_proposal("price_per_token", "0.10")
        assert action.decision == PolicyDecision.COUNTER
        assert action.counter_value == "0.50"

    def test_counter_above_max(self, engine):
        action = engine.evaluate_proposal("price_per_token", "10.00")
        assert action.decision == PolicyDecision.COUNTER
        assert action.counter_value == "2.00"

    def test_refer_to_llm_in_ambiguous_zone(self, engine):
        # Within 20% above max (2.00 * 1.2 = 2.40)
        action = engine.evaluate_proposal("price_per_token", "2.20")
        assert action.decision == PolicyDecision.REFER_TO_LLM
        assert action.confidence < 1.0


class TestQuantityEvaluation:

    @pytest.fixture
    def engine(self):
        return PolicyEngine(PolicyConfig(
            min_quantity=1000,
            max_quantity=500_000,
        ))

    def test_accept_within_range(self, engine):
        action = engine.evaluate_proposal("quantity", "100000")
        assert action.decision == PolicyDecision.ACCEPT

    def test_reject_below_min(self, engine):
        action = engine.evaluate_proposal("quantity", "10")
        assert action.decision == PolicyDecision.REJECT

    def test_counter_above_max(self, engine):
        action = engine.evaluate_proposal("quantity", "1000000")
        assert action.decision == PolicyDecision.COUNTER


class TestSlippageEvaluation:

    @pytest.fixture
    def engine(self):
        return PolicyEngine(PolicyConfig(
            min_slippage_bps=10,
            max_slippage_bps=200,
        ))

    def test_accept_within_range(self, engine):
        action = engine.evaluate_proposal("max_slippage_bps", "50")
        assert action.decision == PolicyDecision.ACCEPT

    def test_counter_too_tight(self, engine):
        action = engine.evaluate_proposal("max_slippage_bps", "2")
        assert action.decision == PolicyDecision.COUNTER
        assert action.counter_value == "10"

    def test_counter_too_wide(self, engine):
        action = engine.evaluate_proposal("max_slippage_bps", "1000")
        assert action.decision == PolicyDecision.COUNTER

    def test_cross_field_tranches_widen_max(self, engine):
        """More tranches → wider acceptable slippage."""
        # With 3 tranches: max = 200 * (1 + 0.2 * 2) = 280
        action = engine.evaluate_proposal(
            "max_slippage_bps", "250",
            current_values={"execution_tranches": "3"},
        )
        assert action.decision == PolicyDecision.ACCEPT


class TestEscrowEvaluation:

    @pytest.fixture
    def engine(self):
        return PolicyEngine(PolicyConfig(
            min_escrow_pct=Decimal("20.0"),
            max_escrow_pct=Decimal("80.0"),
        ))

    def test_accept_within_range(self, engine):
        action = engine.evaluate_proposal("escrow_pct", "50.0")
        assert action.decision == PolicyDecision.ACCEPT

    def test_counter_too_low(self, engine):
        action = engine.evaluate_proposal("escrow_pct", "5.0")
        assert action.decision == PolicyDecision.COUNTER
        assert action.counter_value == "20.0"

    def test_counter_too_high(self, engine):
        action = engine.evaluate_proposal("escrow_pct", "95.0")
        assert action.decision == PolicyDecision.COUNTER


class TestPenaltyEvaluation:

    @pytest.fixture
    def engine(self):
        return PolicyEngine(PolicyConfig(
            min_penalty_bps=50,
            max_penalty_bps=500,
        ))

    def test_accept_within_range(self, engine):
        action = engine.evaluate_proposal("penalty_bps", "200")
        assert action.decision == PolicyDecision.ACCEPT

    def test_counter_too_low(self, engine):
        action = engine.evaluate_proposal("penalty_bps", "10")
        assert action.decision == PolicyDecision.COUNTER

    def test_counter_too_high(self, engine):
        action = engine.evaluate_proposal("penalty_bps", "2000")
        assert action.decision == PolicyDecision.COUNTER

    def test_cross_field_low_escrow_raises_min_penalty(self, engine):
        """Low escrow → demand higher penalty (substitute trust)."""
        action = engine.evaluate_proposal(
            "penalty_bps", "100",
            current_values={"escrow_pct": "15"},  # Below 30% threshold
        )
        assert action.decision == PolicyDecision.COUNTER
        assert action.counter_value == "200"  # Raised min


class TestOracleEvaluation:

    def test_approved_oracle(self):
        engine = PolicyEngine(PolicyConfig(
            approved_oracles={"uniswap_v3", "chainlink"}
        ))
        action = engine.evaluate_proposal("price_oracle_source", "uniswap_v3")
        assert action.decision == PolicyDecision.ACCEPT

    def test_unapproved_oracle(self):
        engine = PolicyEngine(PolicyConfig(
            approved_oracles={"chainlink"}
        ))
        action = engine.evaluate_proposal("price_oracle_source", "uniswap_v3")
        assert action.decision == PolicyDecision.COUNTER

    def test_unknown_oracle(self):
        engine = PolicyEngine(PolicyConfig())
        action = engine.evaluate_proposal("price_oracle_source", "crystal_ball")
        assert action.decision == PolicyDecision.REJECT


class TestSettlementWindowEvaluation:

    @pytest.fixture
    def engine(self):
        return PolicyEngine(PolicyConfig(
            min_settlement_secs=30,
            max_settlement_secs=600,
        ))

    def test_accept_within_range(self, engine):
        action = engine.evaluate_proposal("settlement_window_secs", "120")
        assert action.decision == PolicyDecision.ACCEPT

    def test_reject_below_min(self, engine):
        action = engine.evaluate_proposal("settlement_window_secs", "5")
        assert action.decision == PolicyDecision.REJECT


class TestMinFillEvaluation:

    def test_accept_valid_fill(self):
        engine = PolicyEngine(PolicyConfig(min_fill_pct=Decimal("20.0")))
        action = engine.evaluate_proposal(
            "min_fill_quantity", "30000",
            current_values={"quantity": "100000"},
        )
        assert action.decision == PolicyDecision.ACCEPT

    def test_counter_fill_too_low(self):
        engine = PolicyEngine(PolicyConfig(min_fill_pct=Decimal("50.0")))
        action = engine.evaluate_proposal(
            "min_fill_quantity", "10000",
            current_values={"quantity": "100000"},
        )
        assert action.decision == PolicyDecision.COUNTER
        assert action.counter_value == "50000"


# ── Market Data Tests ─────────────────────────────────────────────

class TestMockDEXOracle:

    def test_slippage_increases_with_block_size(self):
        oracle = MockDEXOracle(
            base_price=Decimal("1.00"),
            liquidity_depth=Decimal("500000"),
        )
        small = oracle.get_snapshot(10_000)
        large = oracle.get_snapshot(100_000)
        assert large.dex_slippage_bps > small.dex_slippage_bps

    def test_seller_gets_less_on_dex(self):
        oracle = MockDEXOracle(base_price=Decimal("1.00"))
        effective = oracle.compute_effective_dex_price(100_000, "sell")
        assert effective < Decimal("1.00")

    def test_buyer_pays_more_on_dex(self):
        oracle = MockDEXOracle(base_price=Decimal("1.00"))
        effective = oracle.compute_effective_dex_price(100_000, "buy")
        assert effective > Decimal("1.00")

    def test_otc_savings_positive_when_better_than_dex(self):
        oracle = MockDEXOracle(
            base_price=Decimal("1.00"),
            liquidity_depth=Decimal("500000"),
        )
        # Seller OTC at $0.99 vs DEX effective ~$0.80 → positive savings
        savings = oracle.compute_savings(Decimal("0.99"), 100_000, "sell")
        assert savings > 0


# ── DualAgentSimulator Tests ────────────────────────────────────

class TestDualAgentSimulator:
    """End-to-end two-agent negotiation."""

    def test_full_auto_negotiation_reaches_agreement(self):
        """Two agents with compatible policies should agree on all fields."""
        orch = create_otc_orchestrator()

        sim = DualAgentSimulator(
            orchestrator=orch,
            seller_config=PolicyConfig(),
            buyer_config=PolicyConfig(),
        )

        actions = sim.run_negotiation(
            entity_id="SIM-001",
            seller_initial_values={
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
            },
        )

        assert len(actions) > 0

        statuses = orch.get_all_field_statuses("SIM-001")
        agreed_count = sum(
            1 for s in statuses.values()
            if s == FieldNegotiationStatus.AGREED
        )
        assert agreed_count == 12, (
            f"Expected 12 agreed fields, got {agreed_count}. "
            f"Statuses: {statuses}"
        )

    def test_manual_mode_does_not_act(self):
        orch = create_otc_orchestrator()
        sim = DualAgentSimulator(orchestrator=orch)
        sim.buyer.state.mode = AgentMode.MANUAL

        actions = sim.run_negotiation(
            entity_id="SIM-002",
            seller_initial_values={
                "price_per_token": "1.05",
                "quantity": "100000",
            },
        )

        human_actions = [a for a in actions if a.decision == PolicyDecision.AWAIT_HUMAN]
        assert len(human_actions) > 0

    def test_paused_agent_does_not_act(self):
        orch = create_otc_orchestrator()
        sim = DualAgentSimulator(orchestrator=orch)
        sim.buyer.state.paused = True

        actions = sim.run_negotiation(
            entity_id="SIM-003",
            seller_initial_values={
                "price_per_token": "1.05",
                "quantity": "100000",
            },
        )

        human_actions = [a for a in actions if a.decision == PolicyDecision.AWAIT_HUMAN]
        assert len(human_actions) > 0

    def test_counter_proposal_on_price(self):
        """Buyer with strict price limit should counter-propose."""
        orch = create_otc_orchestrator()

        sim = DualAgentSimulator(
            orchestrator=orch,
            buyer_config=PolicyConfig(
                max_price=Decimal("0.90"),  # Very strict
            ),
        )

        actions = sim.run_negotiation(
            entity_id="SIM-004",
            seller_initial_values={
                "price_per_token": "5.00",  # Way above buyer's max
            },
        )

        counter_actions = [a for a in actions if a.decision == PolicyDecision.COUNTER]
        assert len(counter_actions) > 0
