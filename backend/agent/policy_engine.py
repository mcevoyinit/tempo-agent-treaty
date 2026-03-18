"""
Policy Engine — Deterministic Agent Rules for OTC Block Trades
================================================================

Evaluates proposals against hard-coded rules. No LLM, no randomness.
Returns one of: ACCEPT / REJECT / COUNTER / REFER_TO_LLM.

The policy engine enforces HARD LIMITS. The strategy layer (Phase 2)
handles cross-field concessions within these limits.

Key design: agents don't evaluate 12 fields independently. The policy
engine considers context — e.g., if price is aggressive, it can relax
on slippage. This creates the natural concession dynamics.
"""

from decimal import Decimal
from typing import Any, Optional

from .types import (
    AgentAction,
    PolicyConfig,
    PolicyDecision,
)


class PolicyEngine:
    """Deterministic policy evaluation for OTC block trade proposals."""

    def __init__(self, config: PolicyConfig):
        self.config = config

    def evaluate_proposal(
        self,
        field_path: str,
        proposed_value: Any,
        current_values: Optional[dict[str, Any]] = None,
    ) -> AgentAction:
        """
        Evaluate a single field proposal against policy rules.

        current_values provides context for cross-field decisions.
        """
        current_values = current_values or {}

        evaluators = {
            "price_per_token": self._evaluate_price,
            "quantity": self._evaluate_quantity,
            "min_fill_quantity": self._evaluate_min_fill,
            "partial_fill_allowed": self._evaluate_boolean,
            "settlement_window_secs": self._evaluate_settlement_window,
            "execution_tranches": self._evaluate_tranches,
            "max_slippage_bps": self._evaluate_slippage,
            "escrow_pct": self._evaluate_escrow,
            "penalty_bps": self._evaluate_penalty,
            "expire_after_secs": self._evaluate_expire,
            "price_oracle_source": self._evaluate_oracle,
            "twap_window_mins": self._evaluate_twap,
        }

        evaluator = evaluators.get(field_path)
        if evaluator:
            return evaluator(field_path, proposed_value, current_values)

        # Unknown field — accept if non-empty
        if proposed_value and str(proposed_value).strip():
            return AgentAction(
                decision=PolicyDecision.ACCEPT,
                field_path=field_path,
                original_value=proposed_value,
                reasoning="No specific policy rule — accepting non-empty value",
            )
        return AgentAction(
            decision=PolicyDecision.REJECT,
            field_path=field_path,
            original_value=proposed_value,
            reasoning="Empty value rejected",
        )

    # ── Economics Evaluators ──────────────────────────────────────

    def _evaluate_price(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        """
        Price evaluation with REFER_TO_LLM ambiguous zone.

        If price is within 20% above max → ambiguous, LLM decides.
        This models: "it's expensive but maybe worth it given the block size."
        """
        try:
            price = Decimal(str(value))
        except Exception:
            return self._reject(field_path, value, f"Invalid price: {value}")

        if price < self.config.min_price:
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(self.config.min_price),
                reasoning=f"Price too low ({price} < {self.config.min_price} minimum)",
            )
        if price > self.config.max_price:
            # Ambiguous zone: within 20% above max
            threshold = self.config.max_price * Decimal("1.2")
            if price <= threshold:
                return AgentAction(
                    decision=PolicyDecision.REFER_TO_LLM,
                    field_path=field_path,
                    original_value=value,
                    reasoning=f"Price in ambiguous zone ({price}, max is {self.config.max_price})",
                    confidence=0.5,
                )
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(self.config.max_price),
                reasoning=f"Price too high ({price} > {self.config.max_price} maximum)",
            )
        return self._accept(field_path, value, f"Price acceptable ({price})")

    def _evaluate_quantity(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        return self._evaluate_int_range(
            field_path, value,
            min_val=self.config.min_quantity,
            max_val=self.config.max_quantity,
            counter_val=self.config.max_quantity,
            label="quantity",
        )

    def _evaluate_min_fill(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        """Min fill validated against quantity if available."""
        try:
            fill = int(value)
        except (ValueError, TypeError):
            return self._reject(field_path, value, f"Invalid min fill: {value}")

        # If we know the quantity, validate fill as percentage
        qty_str = ctx.get("quantity")
        if qty_str:
            try:
                qty = int(qty_str)
                fill_pct = Decimal(fill) / Decimal(qty) * 100
                if fill_pct < self.config.min_fill_pct:
                    min_fill = int(qty * self.config.min_fill_pct / 100)
                    return AgentAction(
                        decision=PolicyDecision.COUNTER,
                        field_path=field_path,
                        original_value=value,
                        counter_value=str(min_fill),
                        reasoning=f"Min fill too low ({fill_pct:.0f}% of quantity, need {self.config.min_fill_pct}%)",
                    )
            except (ValueError, ZeroDivisionError):
                pass

        if fill < 1:
            return self._reject(field_path, value, "Min fill must be positive")
        return self._accept(field_path, value, f"Min fill acceptable ({fill})")

    # ── Execution Evaluators ──────────────────────────────────────

    def _evaluate_settlement_window(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        return self._evaluate_int_range(
            field_path, value,
            min_val=self.config.min_settlement_secs,
            max_val=self.config.max_settlement_secs,
            counter_val=self.config.max_settlement_secs,
            label="settlement window (secs)",
        )

    def _evaluate_tranches(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        return self._evaluate_int_range(
            field_path, value,
            min_val=1,
            max_val=self.config.max_tranches,
            counter_val=1,
            label="execution tranches",
        )

    def _evaluate_slippage(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        """
        Slippage evaluation with cross-field awareness.

        If execution_tranches > 1, wider slippage is acceptable
        because each tranche has less market impact.
        """
        try:
            bps = int(value)
        except (ValueError, TypeError):
            return self._reject(field_path, value, f"Invalid slippage: {value}")

        effective_max = self.config.max_slippage_bps
        # Cross-field: more tranches = wider acceptable slippage
        tranches_str = ctx.get("execution_tranches")
        if tranches_str:
            try:
                tranches = int(tranches_str)
                if tranches > 1:
                    effective_max = int(effective_max * (1 + 0.2 * (tranches - 1)))
            except ValueError:
                pass

        if bps < self.config.min_slippage_bps:
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(self.config.min_slippage_bps),
                reasoning=f"Slippage too tight ({bps}bps < {self.config.min_slippage_bps}bps minimum)",
            )
        if bps > effective_max:
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(effective_max),
                reasoning=f"Slippage too wide ({bps}bps > {effective_max}bps maximum)",
            )
        return self._accept(field_path, value, f"Slippage acceptable ({bps}bps)")

    def _evaluate_boolean(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        return self._accept(field_path, value, "Boolean preference accepted")

    # ── Trust Evaluators ──────────────────────────────────────────

    def _evaluate_escrow(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        try:
            pct = Decimal(str(value))
        except Exception:
            return self._reject(field_path, value, f"Invalid escrow %: {value}")

        if pct < self.config.min_escrow_pct:
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(self.config.min_escrow_pct),
                reasoning=f"Escrow too low ({pct}% < {self.config.min_escrow_pct}% minimum)",
            )
        if pct > self.config.max_escrow_pct:
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(self.config.max_escrow_pct),
                reasoning=f"Escrow too high ({pct}% > {self.config.max_escrow_pct}% maximum)",
            )
        return self._accept(field_path, value, f"Escrow acceptable ({pct}%)")

    def _evaluate_penalty(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        """
        Penalty evaluation with cross-field awareness.

        If escrow is low, penalty should be higher (substitute trust mechanisms).
        """
        try:
            bps = int(value)
        except (ValueError, TypeError):
            return self._reject(field_path, value, f"Invalid penalty: {value}")

        effective_min = self.config.min_penalty_bps
        # Cross-field: low escrow → demand higher penalty
        escrow_str = ctx.get("escrow_pct")
        if escrow_str:
            try:
                escrow = Decimal(str(escrow_str))
                if escrow < Decimal("30"):
                    effective_min = max(effective_min, 200)
            except Exception:
                pass

        if bps < effective_min:
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(effective_min),
                reasoning=f"Penalty too low ({bps}bps < {effective_min}bps minimum"
                + (" — compensating for low escrow)" if effective_min > self.config.min_penalty_bps else ")"),
            )
        if bps > self.config.max_penalty_bps:
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(self.config.max_penalty_bps),
                reasoning=f"Penalty too high ({bps}bps > {self.config.max_penalty_bps}bps maximum)",
            )
        return self._accept(field_path, value, f"Penalty acceptable ({bps}bps)")

    def _evaluate_expire(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        return self._evaluate_int_range(
            field_path, value,
            min_val=self.config.min_expire_secs,
            max_val=self.config.max_expire_secs,
            counter_val=300,
            label="expiry (secs)",
        )

    # ── Market Reference Evaluators ───────────────────────────────

    def _evaluate_oracle(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        source = str(value).lower()
        allowed = {"uniswap_v3", "chainlink", "twap_custom"}
        if source not in allowed:
            return self._reject(field_path, value, f"Unknown oracle: {value}")

        if source in self.config.approved_oracles:
            return self._accept(field_path, value, f"Oracle '{source}' approved")
        return AgentAction(
            decision=PolicyDecision.COUNTER,
            field_path=field_path,
            original_value=value,
            counter_value=sorted(self.config.approved_oracles)[0],
            reasoning=f"Oracle '{source}' not approved (accepted: {self.config.approved_oracles})",
        )

    def _evaluate_twap(
        self, field_path: str, value: Any, ctx: dict
    ) -> AgentAction:
        return self._evaluate_int_range(
            field_path, value,
            min_val=self.config.min_twap_mins,
            max_val=self.config.max_twap_mins,
            counter_val=self.config.max_twap_mins,
            label="TWAP window (mins)",
        )

    # ── Helpers ──────────────────────────────────────────────────

    def _evaluate_int_range(
        self,
        field_path: str,
        value: Any,
        min_val: int,
        max_val: int,
        counter_val: int,
        label: str,
    ) -> AgentAction:
        try:
            n = int(value)
        except (ValueError, TypeError):
            return self._reject(field_path, value, f"Invalid {label}: {value}")

        if n < min_val:
            return AgentAction(
                decision=PolicyDecision.REJECT,
                field_path=field_path,
                original_value=value,
                reasoning=f"{label} below minimum ({n} < {min_val})",
            )
        if n > max_val:
            return AgentAction(
                decision=PolicyDecision.COUNTER,
                field_path=field_path,
                original_value=value,
                counter_value=str(counter_val),
                reasoning=f"{label} exceeds maximum ({n} > {max_val})",
            )
        return self._accept(field_path, value, f"{label} within limits ({n})")

    def _accept(self, field_path: str, value: Any, reason: str) -> AgentAction:
        return AgentAction(
            decision=PolicyDecision.ACCEPT,
            field_path=field_path,
            original_value=value,
            reasoning=reason,
        )

    def _reject(self, field_path: str, value: Any, reason: str) -> AgentAction:
        return AgentAction(
            decision=PolicyDecision.REJECT,
            field_path=field_path,
            original_value=value,
            reasoning=reason,
        )
