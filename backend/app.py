"""
Tempo Agent Treaty — FastAPI Application
==========================================

Main application that wires:
    - OTCBlockTrade entity config (Vellum negotiation engine)
    - Negotiation routes (propose/accept/reject/status)
    - Trade CRUD (in-memory)
    - Agent control + market data
    - Settlement bridge
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import create_otc_orchestrator
from backend.routes.negotiation import create_negotiation_router
from backend.routes.trades import create_trades_router
from backend.routes.agent import create_agent_router
from backend.routes.settlement import create_settlement_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize shared state."""
    # Single orchestrator instance for the demo (in-memory, no DB)
    orchestrator = create_otc_orchestrator()

    # In-memory trade store: {trade_id: trade_dict}
    trade_store: dict[str, dict[str, Any]] = {}

    # Attach to app state
    app.state.orchestrator = orchestrator
    app.state.trade_store = trade_store

    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Tempo Agent Treaty",
        description="Agent-to-Agent OTC Block Trading with Vellum negotiation engine + Tempo settlement",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount route modules
    app.include_router(create_negotiation_router(), prefix="/api/negotiation", tags=["negotiation"])
    app.include_router(create_trades_router(), prefix="/api/trades", tags=["trades"])
    app.include_router(create_agent_router(), prefix="/api/agent", tags=["agent"])
    app.include_router(create_settlement_router(), prefix="/api/settlement", tags=["settlement"])

    @app.get("/health")
    async def health():
        return {"status": "ok", "engine": "vellum"}

    return app


app = create_app()
