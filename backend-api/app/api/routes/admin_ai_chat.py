"""KB-096 Phase 3: Admin AI chat API (SOC roles, feature-flagged)."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import require_roles
from app.api.routes.admin import ADMIN_SOC_ROLES
from app.services import ai_admin_chat

router = APIRouter(prefix="/admin/ai", tags=["admin-ai-chat"])


class AdminAiChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=3, max_length=4000)
    tenant_id: Optional[UUID] = None
    tenant_short_code: Optional[str] = Field(default=None, max_length=64)


@router.get("/chat/status")
def admin_ai_chat_status(
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    return {
        "enabled": ai_admin_chat.ai_chat_enabled(),
        "message": (
            "AI Assistant is available."
            if ai_admin_chat.ai_chat_enabled()
            else "AI Assistant is disabled (set AI_CHAT_ENABLED=true after Ollama is validated)."
        ),
    }


@router.post("/chat")
def admin_ai_chat(
    payload: AdminAiChatRequest,
    current_user: Dict[str, Any] = Depends(require_roles(*ADMIN_SOC_ROLES)),
) -> Dict[str, Any]:
    _ = current_user
    if not ai_admin_chat.ai_chat_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI chat is disabled (AI_CHAT_ENABLED=false)",
        )
    try:
        result = ai_admin_chat.answer_soc_question(
            question=payload.message,
            tenant_id=str(payload.tenant_id) if payload.tenant_id else None,
            tenant_short_code=payload.tenant_short_code,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return result
