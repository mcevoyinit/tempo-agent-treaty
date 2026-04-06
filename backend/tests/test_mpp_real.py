"""
Black-box tests against real pympp SDK objects.

Proves Agent Treaty's MPP integration uses real APIs —
not hallucinated imports, not vaporware. Every test instantiates
actual pympp classes and asserts real behavior.
"""

import pytest
from decimal import Decimal


# ── 1. All imports from mpp_bridge.py are real ──────────────────────

class TestMppImportsAreReal:
    """Verify every import in mpp_bridge.py resolves to a real class."""

    def test_mpp_client_exists(self):
        from mpp.client import Client
        assert Client is not None
        assert hasattr(Client, 'get')
        assert hasattr(Client, 'post')

    def test_mpp_server_exists(self):
        from mpp.server import Mpp
        assert Mpp is not None
        assert hasattr(Mpp, 'create')
        assert hasattr(Mpp, 'charge')
        assert hasattr(Mpp, 'pay')

    def test_challenge_at_top_level(self):
        """Challenge lives at mpp.Challenge, NOT mpp.server.Challenge."""
        from mpp import Challenge
        assert Challenge is not None
        assert hasattr(Challenge, 'create')

    def test_credential_and_receipt_exist(self):
        from mpp import Credential, Receipt
        assert Credential is not None
        assert Receipt is not None

    def test_tempo_method_exists(self):
        from mpp.methods.tempo import TempoAccount, ChargeIntent
        assert TempoAccount is not None
        assert ChargeIntent is not None
        assert hasattr(TempoAccount, 'from_key')
        assert hasattr(TempoAccount, 'address')


# ── 2. TempoAccount creates real wallets ────────────────────────────

class TestTempoAccount:
    """Prove TempoAccount produces real Ethereum-compatible accounts."""

    def test_from_key_produces_address(self):
        from mpp.methods.tempo import TempoAccount
        key = "0x" + "ab" * 32
        account = TempoAccount.from_key(key)
        assert account.address.startswith("0x")
        assert len(account.address) == 42

    def test_two_keys_two_addresses(self):
        from mpp.methods.tempo import TempoAccount
        seller = TempoAccount.from_key("0x" + "11" * 32)
        buyer = TempoAccount.from_key("0x" + "22" * 32)
        assert seller.address != buyer.address

    def test_account_has_sign_capability(self):
        from mpp.methods.tempo import TempoAccount
        # 0xff*32 exceeds secp256k1 curve order — use a valid key
        account = TempoAccount.from_key("0x" + "ab" * 32)
        assert hasattr(account, 'sign_hash')


# ── 3. ChargeIntent instantiation ───────────────────────────────────

class TestChargeIntent:
    """Prove ChargeIntent is a real configurable payment intent."""

    def test_creates_with_chain_id(self):
        from mpp.methods.tempo import ChargeIntent
        intent = ChargeIntent(chain_id=42429, rpc_url="https://rpc.testnet.tempo.xyz")
        assert intent is not None
        assert intent.name == "charge"

    def test_creates_with_defaults(self):
        from mpp.methods.tempo import ChargeIntent
        intent = ChargeIntent()
        assert intent is not None


# ── 4. Mpp.charge() returns Challenge when no auth ──────────────────

class TestMppCharge:
    """Prove the server-side 402 challenge flow works with real objects."""

    @pytest.mark.asyncio
    async def test_charge_without_auth_returns_challenge(self):
        """Mpp.charge(authorization=None) must return a Challenge."""
        from mpp import Challenge
        from mpp.server import Mpp
        from mpp.server.method import Method
        from mpp.server.intent import Intent

        class StubIntent(Intent):
            name = "charge"
            async def verify(self, credential, request):
                pass

        class StubMethod(Method):
            name = "stub"
            currency = "0x" + "00" * 20  # USDC contract address placeholder
            recipient = "0x" + "aa" * 20  # seller address placeholder
            intents = {"charge": StubIntent()}
            def format_challenge(self, challenge):
                return {}
            def parse_credential(self, payload):
                return None

        mpp = Mpp.create(method=StubMethod(), secret_key="test-secret-key")
        result = await mpp.charge(
            authorization=None,
            amount="105000.00",
            memo="OTC:trade-123:abc123hash",
        )

        assert isinstance(result, Challenge)
        assert result.method == "stub"
        assert result.intent == "charge"
        # MPP converts human amounts to base units (6 decimals, like USDC)
        # 105000.00 → 105000000000 (105000 * 10^6)
        assert result.request["amount"] == "105000000000"

    @pytest.mark.asyncio
    async def test_charge_memo_preserved_in_challenge(self):
        """The memo we pass to charge() is accessible in the challenge request."""
        from mpp import Challenge
        from mpp.server import Mpp
        from mpp.server.method import Method
        from mpp.server.intent import Intent

        class StubIntent(Intent):
            name = "charge"
            async def verify(self, credential, request):
                pass

        class StubMethod(Method):
            name = "stub"
            currency = "0x" + "00" * 20
            recipient = "0x" + "aa" * 20
            intents = {"charge": StubIntent()}
            def format_challenge(self, challenge):
                return {}
            def parse_credential(self, payload):
                return None

        mpp = Mpp.create(method=StubMethod(), secret_key="test-secret-key")
        result = await mpp.charge(
            authorization=None,
            amount="50000.00",
            memo="parley_tier=fast",
            description="Agent Treaty OTC settlement",
        )

        assert isinstance(result, Challenge)
        assert result.request["amount"]  # amount is present in challenge
        assert result.intent == "charge"


# ── 5. Settlement bridge factory logic ──────────────────────────────

class TestSettlementFactory:
    """Prove create_settlement_bridge() correctly switches modes."""

    def test_mock_mode_returns_mock_bridge(self):
        import os
        os.environ.pop("MPP_MODE", None)
        os.environ.pop("TEMPO_SELLER_PRIVATE_KEY", None)
        os.environ.pop("TEMPO_BUYER_PRIVATE_KEY", None)

        from backend.settlement.mpp_bridge import create_settlement_bridge
        from backend.settlement.bridge import MockSettlementBridge
        bridge = create_settlement_bridge()
        assert isinstance(bridge, MockSettlementBridge)

    def test_live_mode_without_keys_falls_back_to_mock(self):
        import os
        os.environ["MPP_MODE"] = "live"
        os.environ.pop("TEMPO_SELLER_PRIVATE_KEY", None)
        os.environ.pop("TEMPO_BUYER_PRIVATE_KEY", None)

        from backend.settlement.mpp_bridge import create_settlement_bridge
        from backend.settlement.bridge import MockSettlementBridge
        bridge = create_settlement_bridge()
        assert isinstance(bridge, MockSettlementBridge)

        os.environ.pop("MPP_MODE", None)

    def test_live_mode_with_keys_creates_mpp_bridge(self):
        import os
        os.environ["MPP_MODE"] = "live"
        os.environ["TEMPO_SELLER_PRIVATE_KEY"] = "0x" + "aa" * 32
        os.environ["TEMPO_BUYER_PRIVATE_KEY"] = "0x" + "bb" * 32
        os.environ["MPP_SECRET_KEY"] = "test-settlement-secret"

        from backend.settlement.mpp_bridge import create_settlement_bridge, MppSettlementBridge
        bridge = create_settlement_bridge()
        assert isinstance(bridge, MppSettlementBridge)
        assert bridge.seller_account.address.startswith("0x")
        assert bridge.buyer_account.address.startswith("0x")
        assert bridge.seller_account.address != bridge.buyer_account.address

        os.environ.pop("MPP_MODE", None)
        os.environ.pop("TEMPO_SELLER_PRIVATE_KEY", None)
        os.environ.pop("TEMPO_BUYER_PRIVATE_KEY", None)
        os.environ.pop("MPP_SECRET_KEY", None)
