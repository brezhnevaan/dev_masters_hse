from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_users import FastAPIUsers
from typing import List, Optional
import logging

from app.auth.users import current_active_user, get_current_user_optional
from app.auth.db import User
import fastapi_users
from fastapi.responses import StreamingResponse
from app.database.database import get_async_session
from app.links import service
from app.links.schemas import (
    LinkCreateRequest, LinkCreateResponse,
    LinkUpdateRequest, LinkUpdateResponse,
    LinkStatsResponse, LinkSearchResponse,
    UsersLinksResponse, ExpiredLinksResponse,
    LinkReactivateRequest, LinkReactivateResponse
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/links", tags=["Links"])

@router.post("/shorten", response_model=LinkCreateResponse)
async def create_link(
        data: LinkCreateRequest,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(get_current_user_optional)
):
    logger.info(f"Creating new link for user {user.id if user else 'anonymous'}")
    return await service.create_short_link(data, session, user)

@router.get("/search", response_model=LinkSearchResponse)
async def search_link(
        original_url: str,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Searching for link with original URL: {original_url} by user {user.id}")
    return await service.link_search(original_url, session, user)

@router.delete("/{short_code}")
async def delete_link(
        short_code: str,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Deleting link {short_code} by user {user.id}")
    await service.delete_link(short_code, session, user)
    return {"message": "Ссылка удалена"}

@router.put("/", response_model=LinkUpdateResponse)
async def update_link(
        data: LinkUpdateRequest,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Updating link {data.short_code} by user {user.id}")
    return await service.update_short_code(data, session, user)

@router.get("/{short_code}/stats", response_model=LinkStatsResponse)
async def get_stats(
        short_code: str,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Getting stats for link {short_code} by user {user.id}")
    return await service.get_link_stats(short_code, session, user)

@router.get("/my_links", response_model=UsersLinksResponse)
async def get_my_links(
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Getting all links for user {user.id}")
    return await service.get_users_links(session, user)

@router.get("/my_links/download", response_class=StreamingResponse)
async def download_my_links(
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Downloading links for user {user.id}")
    return await service.download_users_links(session, user)

@router.get("/expired", response_model=ExpiredLinksResponse)
async def get_expired_user_links(
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Getting expired links for user {user.id}")
    return await service.get_expired_links(session, user)

@router.get("/expired/download", response_class=StreamingResponse)
async def download_expired_user_links(
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Downloading expired links for user: {user.id}")
    return await service.download_expired_links(session, user)

@router.put("/expired/reactivate", response_model=LinkReactivateResponse)
async def reactivate_link(
        data: LinkReactivateRequest,
        session: AsyncSession = Depends(get_async_session),
        user: User = Depends(current_active_user)
):
    logger.info(f"Reactivating link {data.id} by user {user.id}")
    return await service.reactivate_link_by_id(data, session, user)

@router.get("/{short_code}", response_model=None)
async def redirect_link(
        short_code: str,
        session: AsyncSession = Depends(get_async_session)
):
    logger.info(f"Redirecting to link with short code: {short_code}")
    return await service.redirect(short_code, session)