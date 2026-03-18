"""
OTC Block Trade — Vellum Entity Configuration
===============================================

Configures the Vellum negotiation engine for **agent-to-agent OTC
block trading of illiquid tokens**.

An OTC block trade is: Agent A has a large position to sell (DAO treasury,
whale, market maker). Agent B wants to accumulate. The block is too large
for AMMs without catastrophic slippage. They negotiate P2P — trading off
price, quantity, timing, trust, and market reference — then settle
atomically on Tempo.

The core insight: OTC isn't just about price. It's about RISK TRANSFER.
Each field represents a different risk type, and agents trade risks
against each other through cross-field concessions.

Parties:
    - seller  (has tokens to liquidate)
    - buyer   (wants to accumulate)

Negotiable fields (12):
    Economics:
        - price_per_token          (core price in quote currency)
        - quantity                 (block size in base token)
        - min_fill_quantity        (floor for partial fills)
    Execution:
        - partial_fill_allowed     (all-or-nothing vs flexible)
        - settlement_window_secs   (time to settle after agreement)
        - execution_tranches       (1 = atomic, 2-5 = split)
        - max_slippage_bps         (price deviation tolerance)
    Trust:
        - escrow_pct               (capital locked up-front)
        - penalty_bps              (cost of backing out)
        - expire_after_secs        (offer validity period)
    Market Reference:
        - price_oracle_source      (uniswap_v3 / chainlink / twap_custom)
        - twap_window_mins         (TWAP averaging period)

Lifecycle:
    INDICATION → NEGOTIATION → AGREED → SETTLING → SETTLED | FAILED

This module is PURE CONFIGURATION — no new code, just wiring existing
Vellum primitives for the OTC block trade domain.
"""

from vellum.negotiation import (
    ConsensusConfig,
    ConsensusEngine,
    FieldStateMachine,
    EntityTypeConfig,
    register_entity_type,
    ProposalManager,
    NegotiationOrchestrator,
    create_bilateral_config,
)


# ═══════════════════════════════════════════════════════════════════
# 1. LIFECYCLE STAGES
# ═══════════════════════════════════════════════════════════════════

OTC_LIFECYCLE_STAGES = (
    "INDICATION",      # Agents discover each other, share interest
    "NEGOTIATION",     # Active bilateral price/terms negotiation
    "AGREED",          # All terms agreed by both agents
    "SETTLING",        # Escrow funded, atomic swap in progress
    "SETTLED",         # Trade completed, tokens swapped
    "FAILED",          # Settlement failed or trade expired
)


# ═══════════════════════════════════════════════════════════════════
# 2. NEGOTIABLE FIELDS
# ═══════════════════════════════════════════════════════════════════

OTC_NEGOTIABLE_FIELDS = (
    # Economics
    "price_per_token",
    "quantity",
    "min_fill_quantity",
    # Execution
    "partial_fill_allowed",
    "settlement_window_secs",
    "execution_tranches",
    "max_slippage_bps",
    # Trust
    "escrow_pct",
    "penalty_bps",
    "expire_after_secs",
    # Market Reference
    "price_oracle_source",
    "twap_window_mins",
)


# ═══════════════════════════════════════════════════════════════════
# 3. FIELD LOCK RULES (when do fields become immutable?)
# ═══════════════════════════════════════════════════════════════════

OTC_LOCK_RULES = {
    # Market reference locks early — must agree on pricing basis first
    "price_oracle_source":     ["NEGOTIATION", "AGREED", "SETTLING"],
    "twap_window_mins":        ["NEGOTIATION", "AGREED", "SETTLING"],
    # Economics lock at AGREED — can't change price after escrow
    "price_per_token":         ["AGREED", "SETTLING"],
    "quantity":                ["AGREED", "SETTLING"],
    "min_fill_quantity":       ["AGREED", "SETTLING"],
    # Execution locks at AGREED
    "partial_fill_allowed":    ["AGREED", "SETTLING"],
    "settlement_window_secs":  ["AGREED", "SETTLING"],
    "execution_tranches":      ["AGREED", "SETTLING"],
    "max_slippage_bps":        ["AGREED", "SETTLING"],
    # Trust locks at AGREED
    "escrow_pct":              ["AGREED", "SETTLING"],
    "penalty_bps":             ["AGREED", "SETTLING"],
    "expire_after_secs":       ["AGREED", "SETTLING"],
}


# ═══════════════════════════════════════════════════════════════════
# 4. MANDATORY FIELDS (what must be AGREED before advancing?)
# ═══════════════════════════════════════════════════════════════════

OTC_MANDATORY_FIELDS = {
    "NEGOTIATION": [
        "price_per_token",
        "quantity",
        "price_oracle_source",
    ],
    "AGREED": [
        "price_per_token",
        "quantity",
        "min_fill_quantity",
        "partial_fill_allowed",
        "settlement_window_secs",
        "execution_tranches",
        "max_slippage_bps",
        "escrow_pct",
        "penalty_bps",
        "expire_after_secs",
        "price_oracle_source",
        "twap_window_mins",
    ],
    "SETTLING": [
        "price_per_token",
        "quantity",
        "min_fill_quantity",
        "partial_fill_allowed",
        "settlement_window_secs",
        "execution_tranches",
        "max_slippage_bps",
        "escrow_pct",
        "penalty_bps",
        "expire_after_secs",
        "price_oracle_source",
        "twap_window_mins",
    ],
}


# ═══════════════════════════════════════════════════════════════════
# 5. CONSENSUS CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

def create_otc_consensus_config() -> ConsensusConfig:
    """
    Create consensus config for bilateral OTC block trade.

    Both buyer and seller must agree on all fields.
    Seller is authoritative (they own the tokens being sold).
    """
    return create_bilateral_config(
        party_a="buyer",
        party_b="seller",
        authoritative_party="seller",
    )


# ═══════════════════════════════════════════════════════════════════
# 6. ENTITY TYPE REGISTRATION
# ═══════════════════════════════════════════════════════════════════

OTC_TRADE_CONFIG = EntityTypeConfig(
    graphql_type="OTCBlockTrade",
    participant_fields={
        "buyer": ("buyerId", "buyer.id"),
        "seller": ("sellerId", "seller.id"),
    },
    source_namespace_field="sellerId",
    reference_fields=frozenset({"buyer", "seller"}),
    field_type_hints={
        "price_per_token": "Float",
        "quantity": "Int",
        "min_fill_quantity": "Int",
        "partial_fill_allowed": "Boolean",
        "settlement_window_secs": "Int",
        "execution_tranches": "Int",
        "max_slippage_bps": "Int",
        "escrow_pct": "Float",
        "penalty_bps": "Int",
        "expire_after_secs": "Int",
        "price_oracle_source": "String",
        "twap_window_mins": "Int",
    },
    lifecycle_stages=OTC_LIFECYCLE_STAGES,
    mandatory_fields={
        status: tuple(fields)
        for status, fields in OTC_MANDATORY_FIELDS.items()
    },
    lock_stages={
        path: tuple(stages)
        for path, stages in OTC_LOCK_RULES.items()
    },
    identity_fields=frozenset({"buyer", "seller"}),
    field_path_mappings={},
)

# Register on import
register_entity_type(OTC_TRADE_CONFIG)


# ═══════════════════════════════════════════════════════════════════
# 7. FACTORY: Create a fully wired OTC negotiation stack
# ═══════════════════════════════════════════════════════════════════

def create_otc_negotiation_stack() -> tuple[ConsensusEngine, FieldStateMachine, ProposalManager]:
    """
    Create a fully wired negotiation stack for OTC block trades.

    Returns:
        Tuple of (consensus_engine, field_state_machine, proposal_manager)
    """
    config = create_otc_consensus_config()
    engine = ConsensusEngine(config=config)
    fsm = FieldStateMachine(
        lock_rules=OTC_LOCK_RULES,
        mandatory_fields=OTC_MANDATORY_FIELDS,
    )
    pm = ProposalManager(
        consensus_engine=engine,
        field_state_machine=fsm,
    )
    return engine, fsm, pm


def create_otc_orchestrator() -> NegotiationOrchestrator:
    """
    Create a fully wired NegotiationOrchestrator for OTC block trades.

    This is the main entry point — wraps consensus, state machine, and
    proposal management into a single in-memory orchestrator.
    """
    return NegotiationOrchestrator(
        consensus_config=create_otc_consensus_config(),
        lock_rules=OTC_LOCK_RULES,
        mandatory_fields=OTC_MANDATORY_FIELDS,
        entity_type="OTCBlockTrade",
    )
