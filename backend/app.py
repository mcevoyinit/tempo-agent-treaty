"""
Tempo Agent Treaty — FastAPI Application
==========================================

Main application that wires:
    - OTCBlockTrade entity config (Vellum negotiation engine)
    - Negotiation routes (propose/accept/reject/status)
    - Trade CRUD (in-memory)
    - Agent control + market data
    - MPP settlement on Tempo chain
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import create_otc_orchestrator
from backend.routes.negotiation import create_negotiation_router
from backend.routes.trades import create_trades_router
from backend.routes.agent import create_agent_router
from backend.routes.settlement import create_settlement_router
from backend.settlement.mpp_bridge import create_settlement_bridge
from backend.agent.market_data import create_market_oracle

logger = logging.getLogger(__name__)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize shared state."""
    orchestrator = create_otc_orchestrator()
    trade_store: dict[str, dict[str, Any]] = {}

    # Settlement bridge: MPP (live) or Mock (demo)
    settlement_bridge = create_settlement_bridge()

    # Market oracle: MPP-gated (live) or Mock (demo)
    market_oracle = create_market_oracle()

    mpp_mode = os.getenv("MPP_MODE", "mock")

    app.state.orchestrator = orchestrator
    app.state.trade_store = trade_store
    app.state.settlement_bridge = settlement_bridge
    app.state.market_oracle = market_oracle
    app.state.mpp_mode = mpp_mode

    logger.info(f"Agent Treaty started: MPP_MODE={mpp_mode}")

    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Tempo Agent Treaty",
        description="Agent-to-Agent OTC Block Trading with Vellum + MPP settlement on Tempo",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(create_negotiation_router(), prefix="/api/negotiation", tags=["negotiation"])
    app.include_router(create_trades_router(), prefix="/api/trades", tags=["trades"])
    app.include_router(create_agent_router(), prefix="/api/agent", tags=["agent"])
    app.include_router(create_settlement_router(), prefix="/api/settlement", tags=["settlement"])

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "engine": "vellum",
            "settlement": os.getenv("MPP_MODE", "mock"),
        }

    return app


app = create_app()
