"""
Agent Negotiation Loop
=======================

The main decision loop. Each agent:
    1. Observes pending proposals
    2. Evaluates via PolicyEngine
    3. Acts (accept/reject/counter) via NegotiationOrchestrator

Two agents (seller + buyer) run in the same process with separate
PolicyConfigs. For the demo, the loop is event-driven — triggered
when proposals arrive rather than polling.
"""

import logging
from typing import Any, Optional

from vellum.negotiation import NegotiationOrchestrator

from .policy_engine import PolicyEngine
from .types import (
    AgentAction,
    AgentMode,
    AgentState,
    PolicyConfig,
    PolicyDecision,
)

logger = logging.getLogger(__name__)


class AgentNegotiator:
    """
    A single negotiating agent (seller or buyer).

    Wraps a PolicyEngine and acts through the NegotiationOrchestrator.
    """

    def __init__(
        self,
        state: AgentState,
        orchestrator: NegotiationOrchestrator,
    ):
        self.state = state
        self.orchestrator = orchestrator
        self.policy_engine = PolicyEngine(state.policy)

    def on_proposal_received(
        self,
        proposal_id: str,
        entity_id: str,
        field_path: str,
        proposed_value: Any,
        proposer_role: str,
        current_values: Optional[dict[str, Any]] = None,
    ) -> AgentAction:
        """
        React to an incoming proposal.

        Returns the action taken (for logging/UI display).
        Does NOT act if the proposer is us (can't accept own proposals).
        """
        if proposer_role == self.state.role:
            return AgentAction(
                decision=PolicyDecision.ACCEPT,
                field_path=field_path,
                original_value=proposed_value,
                reasoning="Own proposal — no action needed",
            )

        if self.state.paused:
            return AgentAction(
                decision=PolicyDecision.AWAIT_HUMAN,
                field_path=field_path,
                original_value=proposed_value,
                reasoning="Agent is paused",
            )

        if self.state.mode == AgentMode.MANUAL:
            return AgentAction(
                decision=PolicyDecision.AWAIT_HUMAN,
                field_path=field_path,
                original_value=proposed_value,
                reasoning="Manual mode — awaiting human decision",
            )

        # Evaluate via policy engine (deterministic, context-aware)
        action = self.policy_engine.evaluate_proposal(
            field_path=field_path,
            proposed_value=proposed_value,
            current_values=current_values,
        )

        # REFER_TO_LLM → auto-counter in FULL_AUTO mode (no real LLM wired)
        if action.decision == PolicyDecision.REFER_TO_LLM and self.state.mode == AgentMode.FULL_AUTO:
            # Split the difference: counter with midpoint of proposed value and policy max
            counter_val = self._compute_midpoint_counter(field_path, proposed_value)
            if counter_val is not None:
                action.decision = PolicyDecision.COUNTER
                action.counter_value = counter_val
                action.reasoning = f"[AUTO-LLM] {action.reasoning} — countering with midpoint"

        # In supervised mode, flag all non-trivial decisions for human
        if self.state.mode == AgentMode.SUPERVISED and action.decision != PolicyDecision.ACCEPT:
            action.decision = PolicyDecision.AWAIT_HUMAN
            action.reasoning = f"[SUPERVISED] {action.reasoning}"
            self._log_action(action)
            return action

        # Execute the decision
        self._execute_action(action, proposal_id, entity_id)
        self._log_action(action)
        return action

    def initiate_proposals(
        self,
        entity_id: str,
        field_values: dict[str, Any],
    ) -> list[AgentAction]:
        """
        Proactively propose values for multiple fields.

        Used when the agent wants to start or continue negotiation.
        """
        actions = []
        for field_path, value in field_values.items():
            result = self.orchestrator.submit_proposal(
                entity_id=entity_id,
                field_path=field_path,
                proposed_value=value,
                proposer_party_id=self.state.party_id,
                proposer_collaborator_id=self.state.collaborator_id,
                proposer_role=self.state.role,
            )
            action = AgentAction(
                decision=PolicyDecision.ACCEPT if result.success else PolicyDecision.REJECT,
                field_path=field_path,
                original_value=value,
                reasoning=f"Initiated proposal: {'success' if result.success else result.error}",
            )
            actions.append(action)
            self._log_action(action)
        return actions

    def _execute_action(
        self, action: AgentAction, proposal_id: str, entity_id: str
    ) -> None:
        """Execute the agent's decision through the orchestrator."""
        if action.decision == PolicyDecision.ACCEPT:
            self.orchestrator.accept_proposal(
                proposal_id=proposal_id,
                acceptor_party_id=self.state.party_id,
                acceptor_collaborator_id=self.state.collaborator_id,
                acceptor_role=self.state.role,
            )
        elif action.decision == PolicyDecision.REJECT:
            self.orchestrator.reject_proposal(
                proposal_id=proposal_id,
                rejector_party_id=self.state.party_id,
                rejector_collaborator_id=self.state.collaborator_id,
                rejector_role=self.state.role,
                reason=action.reasoning,
            )
        elif action.decision == PolicyDecision.COUNTER:
            self.orchestrator.reject_proposal(
                proposal_id=proposal_id,
                rejector_party_id=self.state.party_id,
                rejector_collaborator_id=self.state.collaborator_id,
                rejector_role=self.state.role,
                reason=action.reasoning,
                counter_value=action.counter_value,
            )
        # REFER_TO_LLM and AWAIT_HUMAN don't execute immediately

    def _compute_midpoint_counter(self, field_path: str, proposed_value: Any) -> Optional[str]:
        """Compute a midpoint counter-offer for REFER_TO_LLM decisions."""
        from decimal import Decimal, InvalidOperation
        policy = self.state.policy
        try:
            val = Decimal(str(proposed_value))
        except (InvalidOperation, ValueError):
            return None

        bounds = {
            "price_per_token": (policy.min_price, policy.max_price),
            "escrow_pct": (policy.min_escrow_pct, policy.max_escrow_pct),
        }
        int_bounds = {
            "settlement_window_secs": (policy.min_settlement_secs, policy.max_settlement_secs),
            "penalty_bps": (policy.min_penalty_bps, policy.max_penalty_bps),
            "max_slippage_bps": (policy.min_slippage_bps, policy.max_slippage_bps),
            "twap_window_mins": (policy.min_twap_mins, policy.max_twap_mins),
            "expire_after_secs": (policy.min_expire_secs, policy.max_expire_secs),
        }

        if field_path in bounds:
            lo, hi = bounds[field_path]
            mid = (val + hi) / 2
            return str(mid.quantize(Decimal("0.01")))
        if field_path in int_bounds:
            lo, hi = int_bounds[field_path]
            mid = (int(val) + hi) // 2
            return str(mid)
        return None

    def _log_action(self, action: AgentAction) -> None:
        self.state.total_decisions += 1
        self.state.decisions_log.append(action)
        logger.info(
            f"Agent {self.state.agent_id} [{self.state.role}]: "
            f"{action.decision.value} on {action.field_path} — {action.reasoning}"
        )


class DualAgentSimulator:
    """
    Runs seller and buyer agents against each other.

    Used for the hackathon demo — both agents share the same
    orchestrator and take turns reacting to each other's proposals.
    """

    def __init__(
        self,
        orchestrator: NegotiationOrchestrator,
        seller_config: Optional[PolicyConfig] = None,
        buyer_config: Optional[PolicyConfig] = None,
    ):
        self.orchestrator = orchestrator

        self.seller = AgentNegotiator(
            state=AgentState(
                agent_id="agent-seller",
                role="seller",
                party_id="seller-node",
                collaborator_id="agent-seller-bot",
                policy=seller_config or PolicyConfig(),
            ),
            orchestrator=orchestrator,
        )

        self.buyer = AgentNegotiator(
            state=AgentState(
                agent_id="agent-buyer",
                role="buyer",
                party_id="buyer-node",
                collaborator_id="agent-buyer-bot",
                policy=buyer_config or PolicyConfig(),
            ),
            orchestrator=orchestrator,
        )

    def run_negotiation(
        self,
        entity_id: str,
        seller_initial_values: dict[str, Any],
        max_rounds: int = 10,
    ) -> list[AgentAction]:
        """
        Run a full automated negotiation between seller and buyer.

        1. Seller proposes initial values (seller has the tokens)
        2. Buyer evaluates and responds (accept/counter/reject)
        3. If counter, seller responds
        4. Repeat until all fields agreed or max rounds hit

        Returns the full decision log.
        """
        all_actions: list[AgentAction] = []

        # Step 1: Seller initiates with all field proposals
        init_actions = self.seller.initiate_proposals(entity_id, seller_initial_values)
        all_actions.extend(init_actions)

        # Step 2: Iterative negotiation
        for round_num in range(max_rounds):
            # Get all pending proposals
            pending = []
            for pid, proposal in self.orchestrator._proposals.items():
                from vellum.negotiation import ProposalStatus
                if (
                    proposal.entity_id == entity_id
                    and proposal.status == ProposalStatus.PENDING
                ):
                    pending.append(proposal)

            if not pending:
                logger.info(f"Round {round_num + 1}: No pending proposals — negotiation complete")
                break

            for proposal in pending:
                # Route to the correct agent (the one who didn't propose)
                if proposal.proposer_role == "seller":
                    agent = self.buyer
                else:
                    agent = self.seller

                current_values = dict(seller_initial_values)
                # Update with any agreed values
                agreed = self.orchestrator._agreed_values.get(entity_id, {})
                current_values.update(agreed)

                action = agent.on_proposal_received(
                    proposal_id=proposal.proposal_id,
                    entity_id=entity_id,
                    field_path=proposal.field_path,
                    proposed_value=proposal.proposed_value,
                    proposer_role=proposal.proposer_role,
                    current_values=current_values,
                )
                all_actions.append(action)

        return all_actions
