from fastapi import APIRouter

from app.api.v1.research_runs import router as research_runs_router

router = APIRouter()
router.include_router(research_runs_router, prefix="/research-runs")
