"""
Negotiation Routes
===================

REST endpoints wrapping the Vellum NegotiationOrchestrator.

These match the API contract expected by @vellum/ui's NegotiationService:
    POST /proposals              → submit_proposal
    POST /proposals/{id}/accept  → accept_proposal
    POST /proposals/{id}/reject  → reject_proposal (with optional counter)
    GET  /entity/{id}/status     → get_all_field_statuses
    GET  /entity/{id}/field/{path}/history → proposal history for a field
    GET  /pending                → all pending proposals
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from vellum.negotiation import NegotiationOrchestrator, FieldNegotiationStatus


# ── Request/Response Models ──────────────────────────────────────

class SubmitProposalRequest(BaseModel):
    entity_id: str
    field_path: str
    proposed_value: Any
    proposer_party_id: str
    proposer_collaborator_id: str
    proposer_role: str
    lifecycle_stage: Optional[str] = None


class AcceptProposalRequest(BaseModel):
    acceptor_party_id: str
    acceptor_collaborator_id: str
    acceptor_role: str


class RejectProposalRequest(BaseModel):
    rejector_party_id: str
    rejector_collaborator_id: str
    rejector_role: str
    reason: str
    counter_value: Optional[Any] = None


# ── Router Factory ───────────────────────────────────────────────

def create_negotiation_router() -> APIRouter:
    router = APIRouter()

    def _orch(request: Request) -> NegotiationOrchestrator:
        return request.app.state.orchestrator

    @router.post("/proposals")
    async def submit_proposal(body: SubmitProposalRequest, request: Request):
        orch = _orch(request)
        result = orch.submit_proposal(
            entity_id=body.entity_id,
            field_path=body.field_path,
            proposed_value=body.proposed_value,
            proposer_party_id=body.proposer_party_id,
            proposer_collaborator_id=body.proposer_collaborator_id,
            proposer_role=body.proposer_role,
            lifecycle_stage=body.lifecycle_stage,
        )
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)
        return {
            "success": True,
            "proposal_id": result.proposal.proposal_id if result.proposal else None,
            "field_status": result.field_status.value if result.field_status else None,
        }

    @router.post("/proposals/{proposal_id}/accept")
    async def accept_proposal(proposal_id: str, body: AcceptProposalRequest, request: Request):
        orch = _orch(request)
        result = orch.accept_proposal(
            proposal_id=proposal_id,
            acceptor_party_id=body.acceptor_party_id,
            acceptor_collaborator_id=body.acceptor_collaborator_id,
            acceptor_role=body.acceptor_role,
        )
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)
        return {
            "success": True,
            "consensus_reached": result.consensus_reached,
            "field_status": result.field_status.value if result.field_status else None,
            "pending_approvers": result.pending_approvers,
        }

    @router.post("/proposals/{proposal_id}/reject")
    async def reject_proposal(proposal_id: str, body: RejectProposalRequest, request: Request):
        orch = _orch(request)
        result = orch.reject_proposal(
            proposal_id=proposal_id,
            rejector_party_id=body.rejector_party_id,
            rejector_collaborator_id=body.rejector_collaborator_id,
            rejector_role=body.rejector_role,
            reason=body.reason,
            counter_value=body.counter_value,
        )
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)
        return {
            "success": True,
            "field_status": result.field_status.value if result.field_status else None,
            "counter_proposal_id": (
                result.counter_proposal.proposal_id
                if result.counter_proposal else None
            ),
        }

    @router.get("/entity/{entity_id}/status")
    async def get_entity_status(entity_id: str, request: Request):
        orch = _orch(request)
        statuses = orch.get_all_field_statuses(entity_id)
        return {
            "entity_id": entity_id,
            "field_statuses": {
                path: status.value for path, status in statuses.items()
            },
        }

    @router.get("/entity/{entity_id}/can-advance/{target_stage}")
    async def check_can_advance(entity_id: str, target_stage: str, request: Request):
        orch = _orch(request)
        can_advance, blocking = orch.check_can_advance(
            target_stage=target_stage,
            entity_id=entity_id,
        )
        return {
            "can_advance": can_advance,
            "blocking_fields": blocking,
        }

    return router
