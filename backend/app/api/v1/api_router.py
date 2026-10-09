from fastapi import APIRouter
from backend.app.api.v1.auth import router as auth_router
from backend.app.api.v1.organizations import router as org_router
from backend.app.api.v1.leads import router as leads_router
from backend.app.api.v1.calls import router as calls_router
from backend.app.api.v1.analytics import router as analytics_router
from backend.app.api.v1.knowledge import router as knowledge_router
from backend.app.telephony.webhooks import router as telephony_router

api_v1_router = APIRouter(prefix="/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(org_router)
api_v1_router.include_router(leads_router)
api_v1_router.include_router(calls_router)
api_v1_router.include_router(analytics_router)
api_v1_router.include_router(knowledge_router)
api_v1_router.include_router(telephony_router)
