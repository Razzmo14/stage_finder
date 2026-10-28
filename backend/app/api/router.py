"""API router: all /api/v1 subrouters."""

from fastapi import APIRouter

from app.api import llm_settings

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(llm_settings.router)
