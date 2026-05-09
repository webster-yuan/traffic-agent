from fastapi import APIRouter

from app.api.generate import router as generate_router
from app.api.history import router as history_router
from app.api.batch import router as batch_router
from app.api.checkpoints import router as checkpoint_router
from app.api.observability import router as observability_router

router = APIRouter(prefix="/api/v1/traffic", tags=["traffic"])
router.include_router(generate_router)
router.include_router(history_router)
router.include_router(batch_router)
router.include_router(checkpoint_router)
router.include_router(observability_router)
