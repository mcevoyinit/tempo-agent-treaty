"""
Agent Types for OTC Block Trading
===================================

Data structures for the agent policy engine and decision loop.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class PolicyDecision(Enum):
    """What the policy engine decides for a given proposal."""
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    COUNTER = "COUNTER"
    REFER_TO_LLM = "REFER_TO_LLM"
    AWAIT_HUMAN = "AWAIT_HUMAN"


class AgentMode(Enum):
    """Agent operating mode — controls autonomy level."""
    FULL_AUTO = "FULL_AUTO"        # Agent acts without human approval
    SUPERVISED = "SUPERVISED"      # Agent proposes, human approves
    MANUAL = "MANUAL"              # Agent observes, human acts


@dataclass
class PolicyConfig:
    """
    Deterministic guardrails for OTC block trade agents.

    These are HARD LIMITS — the policy engine won't go outside these bounds.
    The strategy layer (concessions) operates WITHIN these limits.
    """
    # Price bounds (per token in quote currency)
    min_price: Decimal = Decimal("0.001")
    max_price: Decimal = Decimal("1000.0")

    # Quantity bounds (tokens)
    min_quantity: int = 100
    max_quantity: int = 10_000_000

    # Min fill as percentage of quantity (for partial fills)
    min_fill_pct: Decimal = Decimal("10.0")

    # Settlement timing bounds
    min_settlement_secs: int = 10
    max_settlement_secs: int = 3600  # 1 hour

    # Execution tranches
    max_tranches: int = 5

    # Slippage tolerance
    min_slippage_bps: int = 5
    max_slippage_bps: int = 500

    # Escrow bounds
    min_escrow_pct: Decimal = Decimal("10.0")
    max_escrow_pct: Decimal = Decimal("100.0")

    # Penalty bounds
    min_penalty_bps: int = 10
    max_penalty_bps: int = 1000

    # Offer validity
    min_expire_secs: int = 30
    max_expire_secs: int = 3600

    # TWAP window
    min_twap_mins: int = 1
    max_twap_mins: int = 1440  # 24 hours

    # Approved oracle sources
    approved_oracles: set[str] = field(
        default_factory=lambda: {"uniswap_v3", "chainlink"}
    )


@dataclass
class AgentAction:
    """Result of the agent's decision on a proposal."""
    decision: PolicyDecision
    field_path: str
    original_value: Any
    counter_value: Optional[Any] = None
    reasoning: str = ""
    confidence: float = 1.0


@dataclass
class AgentState:
    """Current state of an agent."""
    agent_id: str
    role: str  # "seller" or "buyer"
    party_id: str
    collaborator_id: str
    mode: AgentMode = AgentMode.FULL_AUTO
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    paused: bool = False
    total_decisions: int = 0
    decisions_log: list[AgentAction] = field(default_factory=list)
