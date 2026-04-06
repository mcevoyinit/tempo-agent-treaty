# Tempo Agent Treaty

Agentic OTC block trading for illiquid tokens. AI agents negotiate large block trades P2P using the [Vellum](https://github.com/mcevoyinit/vellum) negotiation engine, settling via the Machine Payments Protocol (MPP) on Tempo chain.

![Agent x Agent OTC Block Trading](docs/screenshot.png)

## Quick Start

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Copy and fill in your Tempo testnet keys
cp .env.example .env

# Start (mock mode works without keys)
uvicorn backend.app:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

## Architecture

```
Negotiation (Vellum SDK)          Settlement (MPP on Tempo)
========================          ========================

Seller Agent                      Buyer Agent
    |                                 |
    |  propose price=1.05             |
    |  ─────────────────────►         |
    |                                 |
    |         ◄──── counter price=1.02|
    |                                 |
    |  (PolicyEngine evaluates        |
    |   cross-field concessions)      |
    |                                 |
    |  accept price=1.03              |
    |  ─────────────────────►         |
    |         ◄──── accept            |
    |                                 |
    |  ═══ ALL 12 FIELDS AGREED ═══   |
    |                                 |
    |  SHA256(agreed_terms) ──────►   |
    |                           402 Challenge
    |                          {pay $103K USDC}
    |                                 |
    |                      auto-pay via pympp
    |                                 |
    |                      ◄── Receipt + tx_hash
    |                                 |
    ╰── SETTLED ON TEMPO CHAIN ──────╯
```

**Vellum SDK** — General purpose negotiation engine (Python + React)
- 12 negotiable fields across 4 sections (economics, execution, trust, market reference)
- Cross-field concession logic (wider slippage if more tranches offered)
- Field-level state machines, consensus engine, proposal manager

**Policy Engine** — Hard guardrails per agent
- Deterministic ACCEPT/REJECT/COUNTER decisions
- REFER_TO_LLM for ambiguous zones (auto-counter in full-auto mode)

**MPP Settlement** — Machine Payments Protocol on Tempo chain
- Buyer pays seller via HTTP 402 challenge/response (pympp SDK)
- Content hash of agreed terms embedded in payment memo
- Falls back to mock settlement when no keys configured (`MPP_MODE=mock`)

## How it works

Two agents with competing objectives (best price vs best fill) negotiate a block trade across 12 parameters at once: price, quantity, slippage tolerance, settlement window, tranche count, escrow terms, penalty rate, expiry, oracle source, and TWAP reference. The policy engine enforces cross-field concession logic. When both sides agree, the trade settles atomically via MPP on Tempo chain. Agents also query market data via MPP-gated oracle endpoints to compute their BATNA (Best Alternative To Negotiated Agreement) against AMM execution.

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MPP_MODE` | `live` for real chain, `mock` for demo | `mock` |
| `TEMPO_SELLER_PRIVATE_KEY` | Seller wallet (testnet) | — |
| `TEMPO_BUYER_PRIVATE_KEY` | Buyer wallet (testnet) | — |
| `TEMPO_CHAIN_ID` | Tempo chain ID | `42429` |
| `TEMPO_RPC_URL` | Tempo RPC endpoint | testnet |

## Tests

```bash
python -m pytest backend/tests/ -v  # 74 tests, ~0.3s
```
