from fastapi import FastAPI
import uvicorn

from app.links.router import router as links_router
from app.auth.users import fastapi_users, auth_backend
from app.auth.schemas import UserRead, UserCreate, UserUpdate
from app.links.background_tasks import lifespan
from app.logger import get_logger

logger = get_logger("app")

try:
    logger.info("Initializing FastAPI application")
    app = FastAPI(title="Link Shortener", lifespan=lifespan)

    logger.info("Including auth routers")
    app.include_router(
        fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
    )
    app.include_router(
        fastapi_users.get_register_router(UserRead, UserCreate), prefix="/auth", tags=["auth"]
    )

    logger.info("Including links router")
    app.include_router(links_router)
    logger.info("Application initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize application: {e}")
    raise
