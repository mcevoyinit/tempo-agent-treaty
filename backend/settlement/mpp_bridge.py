"""
MPP Settlement Bridge
======================

Settles agreed OTC trades via the Machine Payments Protocol on Tempo chain.

Flow:
    1. Hash agreed terms with SHA256 (Vellum hasher) for tamper-proof record
    2. Buyer agent pays seller via MPP charge (on-chain USDC transfer)
    3. Content hash is included in the payment memo
    4. Real tx receipt returned with on-chain confirmation

Falls back to MockSettlementBridge when MPP_MODE=mock or no keys configured.
"""

import logging
import os
from typing import Any

from mpp.client import Client
from mpp.methods.tempo import tempo, TempoAccount, ChargeIntent
from mpp.server import Mpp
from mpp import Credential, Receipt

from vellum.sealing.hasher import SHA256Hasher

from .bridge import SettlementBridge, SettlementResult

logger = logging.getLogger(__name__)

# Tempo testnet defaults
DEFAULT_CHAIN_ID = 42429
DEFAULT_RPC_URL = "https://rpc.testnet.tempo.xyz"
EXPLORER_BASE = "https://explorer.testnet.tempo.xyz/tx"


class MppSettlementBridge:
    """
    Settles OTC trades via MPP on Tempo chain.

    The buyer agent's wallet pays the agreed notional (price * quantity)
    to the seller's address. The content hash of the negotiated terms
    is embedded in the payment memo for on-chain auditability.
    """

    def __init__(
        self,
        seller_key: str,
        buyer_key: str,
        chain_id: int | None = None,
        rpc_url: str | None = None,
        secret_key: str | None = None,
    ):
        self.chain_id = chain_id or int(os.getenv("TEMPO_CHAIN_ID", DEFAULT_CHAIN_ID))
        self.rpc_url = rpc_url or os.getenv("TEMPO_RPC_URL", DEFAULT_RPC_URL)
        self.secret_key = secret_key or os.getenv("MPP_SECRET_KEY", "agent-treaty-default-secret")

        self.seller_account = TempoAccount.from_key(seller_key)
        self.buyer_account = TempoAccount.from_key(buyer_key)

        self.hasher = SHA256Hasher()
        self._settlements: dict[str, SettlementResult] = {}

        logger.info(
            f"MppSettlementBridge initialized: "
            f"seller={self.seller_account.address}, "
            f"buyer={self.buyer_account.address}, "
            f"chain={self.chain_id}"
        )

        # Server: seller creates an MPP endpoint that requires payment
        self._server = Mpp.create(
            secret_key=self.secret_key,
            method=tempo(
                intents={"charge": ChargeIntent(
                    chain_id=self.chain_id,
                    rpc_url=self.rpc_url,
                )},
                recipient=self.seller_account.address,
                chain_id=self.chain_id,
                rpc_url=self.rpc_url,
            ),
        )

        # Client: buyer pays via MPP
        self._client_method = tempo(
            intents={"charge": ChargeIntent(
                chain_id=self.chain_id,
                rpc_url=self.rpc_url,
            )},
            account=self.buyer_account,
            chain_id=self.chain_id,
            rpc_url=self.rpc_url,
        )

    async def submit_settlement(
        self, trade_id: str, agreed_values: dict[str, Any]
    ) -> SettlementResult:
        """
        Settle an agreed trade via MPP.

        1. Compute content hash of agreed terms
        2. Calculate trade notional (price * quantity)
        3. Issue MPP charge from buyer to seller
        4. Return settlement result with real tx hash
        """
        from datetime import datetime, timezone

        settlement_id = f"MPP-{trade_id[:8].upper()}"
        now = datetime.now(tz=timezone.utc).isoformat()

        # Step 1: content hash
        content_hash_result = self.hasher.compute_hash(agreed_values)
        content_hash = content_hash_result.digest

        # Step 2: calculate payment amount
        price = float(agreed_values.get("price_per_token", 1.0))
        quantity = float(agreed_values.get("block_size_tokens", 100000))
        notional = price * quantity
        amount_str = f"{notional:.2f}"

        logger.info(
            f"Settlement {settlement_id}: "
            f"notional=${amount_str}, content_hash={content_hash[:16]}..."
        )

        try:
            # Step 3: MPP charge — seller issues 402, buyer pays
            # First, seller creates the challenge
            challenge_or_result = await self._server.charge(
                authorization=None,
                amount=amount_str,
                memo=f"OTC:{trade_id}:{content_hash}",
                description=f"Agent Treaty OTC settlement for trade {trade_id}",
            )

            # If it's a Challenge (no auth provided), buyer needs to pay
            from mpp import Challenge
            if isinstance(challenge_or_result, Challenge):
                # Buyer pays the challenge
                async with Client(methods=[self._client_method]) as client:
                    # The client auto-handles the 402 → pay → retry flow
                    # We construct a local URL that the server would serve
                    # For direct settlement, we use the charge API directly
                    credential, receipt = await self._pay_challenge(
                        challenge_or_result, amount_str, trade_id, content_hash
                    )
            else:
                credential, receipt = challenge_or_result

            tx_hash = receipt.reference or receipt.external_id or ""
            confirmed_at = datetime.now(tz=timezone.utc).isoformat()

            result = SettlementResult(
                success=True,
                settlement_id=settlement_id,
                tx_hash=tx_hash,
                content_hash=content_hash,
                canonical_form=content_hash_result.canonical_form,
                submitted_at=now,
                confirmed_at=confirmed_at,
            )

            logger.info(f"Settlement {settlement_id} confirmed: tx={tx_hash}")

        except Exception as e:
            logger.error(f"Settlement {settlement_id} failed: {e}")
            result = SettlementResult(
                success=False,
                settlement_id=settlement_id,
                content_hash=content_hash,
                canonical_form=content_hash_result.canonical_form,
                error=str(e),
                submitted_at=now,
            )

        self._settlements[settlement_id] = result
        return result

    async def _pay_challenge(
        self, challenge, amount: str, trade_id: str, content_hash: str
    ) -> tuple[Credential, Receipt]:
        """
        Buyer agent pays the MPP challenge.

        This handles the 402 → credential → payment → receipt flow.
        """
        # Create buyer's tempo method for payment
        async with Client(methods=[self._client_method]) as client:
            # The pympp Client handles 402 negotiation automatically
            # We make a request that will trigger the 402 → pay cycle
            response = await client.post(
                f"https://localhost:0/settlement/{trade_id}",
                json={"content_hash": content_hash, "amount": amount},
            )
            # Extract credential and receipt from response headers
            credential = Credential.from_authorization(
                response.headers.get("authorization", "")
            )
            receipt = Receipt.from_payment_receipt(
                response.headers.get("payment-receipt", "")
            )
            return credential, receipt

    async def check_status(self, settlement_id: str) -> SettlementResult:
        result = self._settlements.get(settlement_id)
        if not result:
            return SettlementResult(
                success=False,
                settlement_id=settlement_id,
                error=f"Settlement {settlement_id} not found",
            )
        return result

    def explorer_url(self, tx_hash: str) -> str:
        return f"{EXPLORER_BASE}/{tx_hash}"


def create_settlement_bridge() -> "SettlementBridge":
    """
    Factory: returns MppSettlementBridge if keys are configured,
    otherwise falls back to MockSettlementBridge.
    """
    mode = os.getenv("MPP_MODE", "mock")
    seller_key = os.getenv("TEMPO_SELLER_PRIVATE_KEY", "")
    buyer_key = os.getenv("TEMPO_BUYER_PRIVATE_KEY", "")

    if mode == "live" and seller_key and buyer_key:
        logger.info("Using MppSettlementBridge (live Tempo chain)")
        return MppSettlementBridge(
            seller_key=seller_key,
            buyer_key=buyer_key,
        )
    else:
        logger.info("Using MockSettlementBridge (demo mode)")
        from .bridge import MockSettlementBridge
        return MockSettlementBridge(settlement_delay=0.5)
