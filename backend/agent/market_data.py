"""
DEX Oracle — Market-Aware BATNA for OTC Block Trades
======================================================

Provides price feeds so agents can compute their
Best Alternative To Negotiated Agreement (BATNA).

Two implementations:
    - MockDEXOracle: simulated prices for demo/testing
    - MppMarketOracle: fetches real prices via MPP-gated API

The core insight: an OTC trade only makes sense if BOTH parties
get a better deal than they would on an AMM.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class MarketSnapshot:
    """Live DEX market data for BATNA computation."""
    dex_mid_price: Decimal
    dex_slippage_bps: int
    liquidity_depth_quote: Decimal
    spread_bps: int
    timestamp: str
    block_quantity: int = 0


class MockDEXOracle:
    """
    Simulated DEX oracle with linear slippage model.

    For a block of size Q at liquidity depth L:
        slippage_bps = (Q * mid_price / L) * 10000

    This means larger blocks relative to pool depth suffer
    more slippage — exactly the problem OTC solves.
    """

    def __init__(
        self,
        base_price: Decimal = Decimal("1.00"),
        liquidity_depth: Decimal = Decimal("1000000"),
        spread_bps: int = 30,
    ):
        self.base_price = base_price
        self.liquidity_depth = liquidity_depth
        self.spread_bps = spread_bps

    def get_snapshot(self, block_quantity: int) -> MarketSnapshot:
        """Get market snapshot with slippage computed for a given block size."""
        block_notional = Decimal(block_quantity) * self.base_price
        slippage_bps = int(
            (block_notional / self.liquidity_depth) * 10000
        )

        return MarketSnapshot(
            dex_mid_price=self.base_price,
            dex_slippage_bps=max(1, slippage_bps),
            liquidity_depth_quote=self.liquidity_depth,
            spread_bps=self.spread_bps,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            block_quantity=block_quantity,
        )

    def compute_effective_dex_price(
        self, block_quantity: int, side: str
    ) -> Decimal:
        """
        What price would this side actually get on the DEX?

        Seller gets LESS (mid - slippage - spread/2)
        Buyer pays MORE (mid + slippage + spread/2)
        """
        snapshot = self.get_snapshot(block_quantity)
        slippage_pct = Decimal(snapshot.dex_slippage_bps) / Decimal(10000)
        spread_pct = Decimal(self.spread_bps) / Decimal(20000)  # half spread

        if side == "sell":
            return self.base_price * (1 - slippage_pct - spread_pct)
        else:  # buy
            return self.base_price * (1 + slippage_pct + spread_pct)

    def compute_savings(
        self,
        otc_price: Decimal,
        block_quantity: int,
        side: str,
    ) -> Decimal:
        """
        Dollar savings of OTC price vs DEX execution.

        Positive = OTC is better. Negative = DEX would have been cheaper.
        """
        dex_effective = self.compute_effective_dex_price(block_quantity, side)
        qty = Decimal(block_quantity)

        if side == "sell":
            # Seller wants higher price. OTC - DEX = savings
            return (otc_price - dex_effective) * qty
        else:
            # Buyer wants lower price. DEX - OTC = savings
            return (dex_effective - otc_price) * qty


class MppMarketOracle:
    """
    Fetches market data via MPP-gated oracle endpoints.

    The agent pays a micropayment (e.g. $0.001) per price query
    via the Machine Payments Protocol. Falls back to MockDEXOracle
    if the MPP oracle is unavailable.
    """

    def __init__(
        self,
        oracle_url: str | None = None,
        buyer_key: str | None = None,
        chain_id: int | None = None,
        rpc_url: str | None = None,
    ):
        self.oracle_url = oracle_url or os.getenv(
            "MPP_ORACLE_URL", "https://oracle.mpp.tempo.xyz"
        )
        self._chain_id = chain_id or int(os.getenv("TEMPO_CHAIN_ID", "42429"))
        self._rpc_url = rpc_url or os.getenv(
            "TEMPO_RPC_URL", "https://rpc.testnet.tempo.xyz"
        )
        self._buyer_key = buyer_key or os.getenv("TEMPO_BUYER_PRIVATE_KEY", "")
        self._fallback = MockDEXOracle()
        self._client = None
        self._mpp_available = bool(self._buyer_key)

    async def get_snapshot(self, block_quantity: int) -> MarketSnapshot:
        """
        Get market data, paying via MPP if available.

        The 402 flow:
            GET /v1/price/TEMPO-USDC?qty=100000
            ← 402 {amount: "0.001", token: USDC}
            → auto-pay via pympp Client
            ← 200 {mid: 1.02, slippage_bps: 60, ...}
        """
        if not self._mpp_available:
            return self._fallback.get_snapshot(block_quantity)

        try:
            from mpp.client import Client
            from mpp.methods.tempo import tempo, TempoAccount, ChargeIntent

            account = TempoAccount.from_key(self._buyer_key)
            method = tempo(
                intents={"charge": ChargeIntent(
                    chain_id=self._chain_id,
                    rpc_url=self._rpc_url,
                )},
                account=account,
                chain_id=self._chain_id,
                rpc_url=self._rpc_url,
            )

            async with Client(methods=[method]) as client:
                response = await client.get(
                    f"{self.oracle_url}/v1/price/TEMPO-USDC",
                    params={"qty": str(block_quantity)},
                )

                if response.status_code == 200:
                    data = response.json()
                    return MarketSnapshot(
                        dex_mid_price=Decimal(str(data["mid"])),
                        dex_slippage_bps=int(data.get("slippage_bps", 0)),
                        liquidity_depth_quote=Decimal(
                            str(data.get("liquidity", "1000000"))
                        ),
                        spread_bps=int(data.get("spread_bps", 30)),
                        timestamp=data.get(
                            "timestamp",
                            datetime.now(tz=timezone.utc).isoformat(),
                        ),
                        block_quantity=block_quantity,
                    )

        except Exception as e:
            logger.warning(f"MPP oracle failed, using fallback: {e}")

        return self._fallback.get_snapshot(block_quantity)

    def compute_effective_dex_price(
        self, block_quantity: int, side: str
    ) -> Decimal:
        return self._fallback.compute_effective_dex_price(block_quantity, side)

    def compute_savings(
        self, otc_price: Decimal, block_quantity: int, side: str
    ) -> Decimal:
        return self._fallback.compute_savings(otc_price, block_quantity, side)


def create_market_oracle():
    """Factory: returns MppMarketOracle if configured, else MockDEXOracle."""
    mode = os.getenv("MPP_MODE", "mock")
    if mode == "live" and os.getenv("TEMPO_BUYER_PRIVATE_KEY"):
        logger.info("Using MppMarketOracle (live MPP)")
        return MppMarketOracle()
    logger.info("Using MockDEXOracle (demo mode)")
    return MockDEXOracle()
