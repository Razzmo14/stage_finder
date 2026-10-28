"""API router: all /api/v1 subrouters."""

from fastapi import APIRouter

from app.api import applications, criteria, letters, llm_settings, mail, match, offers, profile

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(llm_settings.router)
api_router.include_router(profile.router)
api_router.include_router(criteria.router)
api_router.include_router(offers.router)
api_router.include_router(match.router)
api_router.include_router(letters.router)
api_router.include_router(applications.router)
api_router.include_router(mail.router)
