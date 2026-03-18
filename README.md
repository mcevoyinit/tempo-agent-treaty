# Tempo Agentic Negotiator

Agentic OTC block trading for illiquid tokens. AI agents negotiate large block trades P2P using the [Vellum](https://github.com/mcevoyinit/vellum) negotiation engine, settling atomically on Tempo chain.

## Quick Start

```bash
# Backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.app:app --reload --port 8000

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

## Architecture

- **Vellum SDK** — Domain-agnostic negotiation engine (Python + React)
- **Policy Engine** — Deterministic guardrails (max spread, position limits)
- **Agent Loop** — Observe → decide → act with human-in-the-loop
- **Tempo Settlement** — Atomic on-chain settlement with content hash verification
