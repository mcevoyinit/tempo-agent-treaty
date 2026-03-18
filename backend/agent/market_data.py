"""
Mock DEX Oracle — Market-Aware BATNA for OTC Block Trades
===========================================================

Simulates a DEX price feed so agents can compute their
Best Alternative To Negotiated Agreement (BATNA).

The core insight: an OTC trade only makes sense if BOTH parties
get a better deal than they would on an AMM. The oracle provides:

    1. Current DEX mid price + slippage for a given block size
    2. Effective price each side would get on-chain (with impact)
    3. Dollar savings of the OTC price vs. DEX execution

Slippage model: linear price impact proportional to
block_notional / liquidity_depth. Simple but realistic enough
for hackathon demo.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal


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
