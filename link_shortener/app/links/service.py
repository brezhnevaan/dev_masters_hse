import csv
import logging
import random
import string
from datetime import datetime, timedelta
from http.client import responses
from io import StringIO
from typing import List, Optional
from urllib.parse import unquote

from fastapi import HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis import asyncio as aioredis

from app.auth.db import User
from app.links.models import Link, ExpiredLink
from app.links.schemas import (LinkCreateRequest, LinkCreateResponse,
                               LinkUpdateRequest, LinkUpdateResponse,
                               LinkStatsResponse,
                               LinkSearch, LinkSearchResponse,
                               UsersLinks, UsersLinksResponse,
                               ExpiredLinks, ExpiredLinksResponse,
                               LinkReactivateRequest, LinkReactivateResponse)

logger = logging.getLogger(__name__)

SHORT_CODE_LENGTH = 10
redis = aioredis.from_url("redis://redis", decode_responses=True)


# Кеширование
async def save_link_in_cache(short_code: str,
                             original_url: str,
                             created_at: datetime,
                             expires_in: int = 3600):
    """Сохраняем короткую ссылку в кэш"""
    logging.info(f"Cache: Saving link {short_code} with original_url={original_url}")
    link_data = {
        "original_url": original_url,
        "created_at": created_at.isoformat()
    }

    await redis.hset(short_code, mapping=link_data)
    await redis.expire(short_code, expires_in)
    logging.info(f"Cache: Link {short_code} saved successfully")


async def save_stats_in_cache(short_code: str,
                              clicks: int,
                              last_click_at: datetime | None = None,
                              is_soft_expire: bool = False,
                              expires_at: datetime | None = None,
                              expires_in: int = 3600):
    """Сохраняет статистику ссылки в кэш"""

    link_stats = {
        "clicks": clicks,
        "is_soft_expire": int(is_soft_expire)
    }

    if last_click_at:
        link_stats["last_click_at"] = last_click_at.isoformat()

    if is_soft_expire and expires_at:
        link_stats["expires_at"] = expires_at.isoformat()
        logging.info(f"Cache: Saving soft expire stats for {short_code}: expires_at={expires_at}, is_soft_expire={is_soft_expire}")
    else:
        logging.info(f"Cache: Saving hard expire stats for {short_code}: is_soft_expire={is_soft_expire}")

    await redis.hset(f"{short_code}:stats", mapping=link_stats)
    await redis.expire(f"{short_code}:stats", expires_in)


async def get_link_from_cache(short_code: str):
    """Отдает данные ссылки из кэша"""
    logging.info(f"Cache: Getting link {short_code}")
    cached_link = await redis.hgetall(short_code)

    if cached_link:
        cached_link["created_at"] = datetime.fromisoformat(cached_link["created_at"])
        logging.info(f"Cache: Link {short_code} found")
        return cached_link

    logging.info(f"Cache: Link {short_code} not found")
    return None


async def get_stats_from_cache(short_code: str):
    """Отдает cтатистику ссылку из кэша"""
    logging.info(f"Cache: Getting stats for {short_code}")
    cached_stats = await redis.hgetall(f"{short_code}:stats")

    if cached_stats:
        cached_stats["is_soft_expire"] = bool(int(cached_stats["is_soft_expire"]))
        logging.info(f"Cache: Stats for {short_code} found: is_soft_expire={cached_stats['is_soft_expire']}")

        if "last_click_at" in cached_stats:
            cached_stats["last_click_at"] = datetime.fromisoformat(cached_stats["last_click_at"])

        if "expires_at" in cached_stats:
            cached_stats["expires_at"] = datetime.fromisoformat(cached_stats["expires_at"])

        return cached_stats

    logging.info(f"Cache: Stats for {short_code} not found")
    return None


async def delete_link_from_cache(short_code: str):
    """Удаляет короткую ссылку из кэша"""
    logging.info(f"Cache: Deleting link {short_code}")
    await redis.delete(short_code)
    await redis.delete(f"{short_code}:stats")
    logging.info(f"Cache: Link {short_code} deleted successfully")


# Обновление статистики в базе для функций из кэша
async def update_stats_in_db(short_code: str,
                             clicks: int,
                             last_click_at: datetime,
                             session: AsyncSession,
                             is_soft_expire: bool = False,
                             expires_at: datetime | None = None,
                             ):
    """Обновляет статистику кликов и дату последнего клика в базе"""
    query = select(Link).where(Link.short_code == short_code)
    result = await session.execute(query)
    link_data = result.scalar_one_or_none()

    if link_data:
        link_data.clicks = clicks
        link_data.last_click_at = last_click_at

        if is_soft_expire and expires_at:
            old_expires_at = link_data.expires_at
            link_data.expires_at = expires_at
            logging.info(f"DB: Updating soft expire for {short_code}: from {old_expires_at} to {expires_at}")
        else:
            logging.info(f"DB: No expires_at update for {short_code}: is_soft_expire={is_soft_expire}")

        await session.commit()


# Основные функции сервиса
async def get_unique_code(session: AsyncSession,
                          length: int = SHORT_CODE_LENGTH
                          ) -> str:
    """Генерирует уникальный короткий код"""
    logging.info("Generating unique code")
    symbols = string.ascii_uppercase + string.digits

    while True:
        code = ''.join(random.choices(symbols, k=length))
        query = select(Link).where(Link.short_code == code)
        result = await session.execute(query)

        if not result.scalar_one_or_none():
            logging.info(f"Generated unique code: {code}")
            return code


async def create_short_link(link_data: LinkCreateRequest,
                            session: AsyncSession,
                            user: User | None = None
                            ) -> LinkCreateResponse:
    """Создает короткую ссылку в базе"""

    alias = link_data.custom_alias

    if not alias:
        short_code = await get_unique_code(session)
    else:
        query = select(Link).where(Link.short_code == alias)
        result = await session.execute(query)

        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Алиас уже существует, выберите новый."
            )

        short_code = alias

    original_url_str = str(link_data.original_url)

    if not link_data.expires_at:
        expires_at = datetime.utcnow() + timedelta(days=14)
        is_soft_expire = True
        logging.info(f"Creating link with soft expire: expires_at={expires_at}, is_soft_expire={is_soft_expire}")
    else:
        try:
            expires_at = link_data.expires_at
            if expires_at.tzinfo is not None:
                logging.error(f"Invalid expires_at format: date contains timezone information")
                raise HTTPException(
                    status_code=400,
                    detail="Дата истечения ссылки должна быть с точностью до минуты. Используйте формат YYYY-MM-DD HH:MM (например, 2025-06-25 15:30)."
                )
            if expires_at.microsecond != 0:
                logging.error(f"Invalid expires_at format: date contains microseconds")
                raise HTTPException(
                    status_code=400,
                    detail="Дата истечения ссылки должна быть с точностью до минуты. Используйте формат YYYY-MM-DD HH:MM (например, 2025-06-25 15:30)."
                )
            is_soft_expire = False
            logging.info(f"Creating link with hard expire: expires_at={expires_at}, is_soft_expire={is_soft_expire}")
        except ValueError as e:
            logging.error(f"Invalid expires_at format: {e}")
            raise HTTPException(
                status_code=400,
                detail="Неверный формат даты истечения ссылки. Используйте формат YYYY-MM-DD HH:MM (например, 2025-06-25 15:30)."
            )

    new_link = Link(
        original_url=original_url_str,
        short_code=short_code,
        expires_at=expires_at,
        is_soft_expire=is_soft_expire,
        user_id=user.id if user else None
    )

    # сохраняем изменения в базу
    session.add(new_link)
    await session.commit()

    return LinkCreateResponse(
        message="Ссылка успешно создана",
        original_url=original_url_str,
        short_code=short_code,
        expires_at=expires_at
    )


async def redirect(short_code: str,
                   session: AsyncSession
                   ) -> RedirectResponse:
    """Перенаправляет на оригинальный адрес, обновляет статистику,
    обновляет expires_at для ссылок с is_soft_expire=True"""

    logging.info(f"Redirect called for short_code: {short_code}")

    cached_link = await get_link_from_cache(short_code)
    cached_stats = await get_stats_from_cache(short_code)

    if cached_link and cached_stats:
        logging.info("Redirecting from cache")
        clicks = int(cached_stats["clicks"])
        clicks += 1
        last_click_at = datetime.utcnow()

        is_soft_expire = bool(int(cached_stats["is_soft_expire"]))
        logging.info(f"Cache: is_soft_expire={is_soft_expire}")

        if is_soft_expire:
            expires_at = datetime.utcnow() + timedelta(days=14)
            logging.info(f"Cache: Updating expires_at to {expires_at}")
            await save_stats_in_cache(short_code, clicks, last_click_at, is_soft_expire, expires_at)
            await update_stats_in_db(short_code, clicks, last_click_at, session, is_soft_expire, expires_at)
        else:
            await save_stats_in_cache(short_code, clicks, last_click_at, is_soft_expire)
            await update_stats_in_db(short_code, clicks, last_click_at, session, is_soft_expire)

        return RedirectResponse(url=cached_link["original_url"])

    query = select(Link).where(Link.short_code == short_code)
    result = await session.execute(query)
    link_data: Link = result.scalar_one_or_none()

    if not link_data or (link_data.expires_at < datetime.utcnow()):
        logging.error(f"Link not found: {short_code}")
        raise HTTPException(status_code=404,
                            detail="Ссылка не найдена. Проверьте введенный алиас, или создайте новый.")

    logging.info(f"DB: is_soft_expire={link_data.is_soft_expire}")
    # Для ссылок, в которых юзер не указал expires_at самостоятельно,
    # устанавливаем expires_at на 14 дней с последнего клика
    if link_data.is_soft_expire:
        old_expires_at = link_data.expires_at
        link_data.expires_at = datetime.utcnow() + timedelta(days=14)
        logging.info(f"DB: Updating expires_at from {old_expires_at} to {link_data.expires_at}")

    link_data.last_click_at = datetime.utcnow()
    link_data.clicks += 1

    # сохраняем изменения в базу
    await session.commit()

    # сохраняем в кэш
    await save_link_in_cache(short_code, link_data.original_url, link_data.created_at)
    if link_data.is_soft_expire:
        await save_stats_in_cache(short_code, link_data.clicks, link_data.last_click_at, link_data.is_soft_expire, link_data.expires_at)
    else:
        await save_stats_in_cache(short_code, link_data.clicks, link_data.last_click_at, link_data.is_soft_expire)

    logging.info(f"Redirecting to: {link_data.original_url}")
    return RedirectResponse(url=link_data.original_url)


async def delete_link(short_code: str,
                      session: AsyncSession,
                      user: User | None = None
                      ) -> None:
    """Удаляет ссылку из базы"""
    logging.info(f"Deleting link {short_code} for user {user.id if user else 'anonymous'}")

    query = select(Link).where(Link.short_code == short_code)
    result = await session.execute(query)
    link_data: Link = result.scalar_one_or_none()

    if not link_data:
        logging.error(f"Link {short_code} not found")
        raise HTTPException(status_code=404,
                            detail="Ссылка не найдена.")

    if link_data.user_id != user.id:
        logging.error(f"User {user.id if user else 'anonymous'} has no access to delete link {short_code}")
        raise HTTPException(status_code=403,
                            detail="Нет доступа к удалению.")

    # удаление из базы
    await session.delete(link_data)
    await session.commit()
    # удаление из кеша
    await delete_link_from_cache(short_code)
    logging.info(f"Link {short_code} deleted successfully")


async def update_short_code(update_data: LinkUpdateRequest,
                            session: AsyncSession,
                            user: User | None = None
                            ) -> LinkUpdateResponse:
    """Обновляет short code существующей в базе ссылки"""
    logging.info(f"Updating short code for {update_data.short_code} to {update_data.new_short_code}")

    query = select(Link).where((Link.short_code == update_data.short_code) & (Link.user_id == user.id))
    result = await session.execute(query)
    link_data: Link = result.scalar_one_or_none()

    if not link_data:
        logging.error(f"Link {update_data.short_code} not found")
        raise HTTPException(
            status_code=404,
            detail=f"Ссылка не найдена {update_data.short_code}."
        )

    if update_data.new_short_code:
        new_short_code = update_data.new_short_code

        conflict_query = select(Link).where(Link.short_code == new_short_code)
        conflict_result = await session.execute(conflict_query)

        if conflict_result.scalar_one_or_none():
            logging.error(f"New short code {new_short_code} already exists")
            raise HTTPException(
                status_code=400,
                detail="Алиас уже существует, выберите другой."
            )
    else:
        new_short_code = await get_unique_code(session)

    link_data.short_code = new_short_code
    await session.commit()

    # удаление из кеша старого short_code
    await delete_link_from_cache(update_data.short_code)
    logging.info(f"Short code updated successfully from {update_data.short_code} to {new_short_code}")

    return LinkUpdateResponse(
        message="Алиас успешно обновлён",
        original_url=link_data.original_url,
        short_code=new_short_code
    )


async def get_link_stats(short_code: str,
                         session: AsyncSession,
                         user: User | None = None
                         ) -> LinkStatsResponse:
    """Возвращает статистику по короткой ссылке"""

    cached_stats = await get_stats_from_cache(short_code)
    cached_link = await get_link_from_cache(short_code)

    if cached_stats and cached_link:
        if "last_click_at" in cached_stats:
            last_click_at = cached_stats["last_click_at"]
        else:
            last_click_at = None

        response_data = {
            "original_url": cached_link["original_url"],
            "short_code": short_code,
            "created_at": cached_link["created_at"],
            "last_click_at": last_click_at,
            "clicks": cached_stats["clicks"]
        }

        return LinkStatsResponse.model_validate(response_data)

    query = select(Link).where(Link.short_code == short_code)
    result = await session.execute(query)
    link_data: Link = result.scalar_one_or_none()

    if not link_data:
        raise HTTPException(
            status_code=404,
            detail="Ссылка не найдена."
        )

    if link_data.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Нет доступа к этой ссылке."
        )

    logging.info(f"Stats: Getting stats for {short_code}: is_soft_expire={link_data.is_soft_expire}, expires_at={link_data.expires_at}")

    # сохраняем в кэш
    await save_link_in_cache(short_code, link_data.original_url, link_data.created_at)
    if link_data.is_soft_expire:
        await save_stats_in_cache(short_code, link_data.clicks, link_data.last_click_at, link_data.is_soft_expire, link_data.expires_at)
    else:
        await save_stats_in_cache(short_code, link_data.clicks, link_data.last_click_at, link_data.is_soft_expire)

    link_data_dict = link_data.__dict__
    return LinkStatsResponse.model_validate(link_data_dict)


async def link_search(original_url: str,
                      session: AsyncSession,
                      user: User | None = None
                      ) -> LinkSearchResponse:
    """Ищет ссылку по оригинальному URL"""
    logging.info(f"Searching for URL: {original_url} for user {user.id if user else 'anonymous'}")

    original_url_decoded = unquote(original_url)
    query = select(Link).where((Link.original_url == original_url_decoded) & (Link.user_id == user.id))
    result = await session.execute(query)
    link_data_list: List[Link] = result.scalars().all()

    if not link_data_list:
        logging.error(f"Link not found for URL: {original_url_decoded}")
        raise HTTPException(
            status_code=404,
            detail=f"Ссылка не найдена {original_url_decoded}."
        )

    logging.info(f"Found {len(link_data_list)} links for URL: {original_url_decoded}")
    links = [LinkSearch.model_validate(link_data.__dict__) for link_data in link_data_list]

    return LinkSearchResponse(links=links)


async def get_users_links(session: AsyncSession,
                          user: User
                          ) -> UsersLinksResponse:
    """Возвращает все созданные авторизованным пользователем ссылки"""
    logging.info(f"Getting all links for user {user.id}")

    if user is None:
        logging.error("Unauthorized attempt to get user links")
        raise HTTPException(
            status_code=401,
            detail="Просмотр доступен только зарегистрированным и авторизованным пользователям."
        )

    query = select(Link).where(Link.user_id == user.id)
    result = await session.execute(query)
    link_data_list: List[Link] = result.scalars().all()

    if not link_data_list:
        logging.info(f"No links found for user {user.id}")
        raise HTTPException(
            status_code=404,
            detail="У вас нет созданных ссылок."
        )

    logging.info(f"Found {len(link_data_list)} links for user {user.id}")
    links = [UsersLinks.model_validate(link_data.__dict__) for link_data in link_data_list]

    return UsersLinksResponse(links=links)


async def download_users_links(session: AsyncSession,
                               user: User
                              ):
    """Возвращает csv-файл с информацией о ссылках пользователя для скачивания"""

    query = select(Link).where(Link.user_id == user.id)
    result = await session.execute(query)
    link_data_list: List[Link] = result.scalars().all()

    if not link_data_list:
        raise HTTPException(
            status_code=404,
            detail="У вас нет созданных ссылок."
        )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Short Code", "Original URL", "Created At", "Expires At", "Clicks", "Last Click At"])

    for link_data in link_data_list:
        writer.writerow([
            link_data.short_code,
            link_data.original_url,
            link_data.created_at,
            link_data.expires_at,
            link_data.clicks,
            link_data.last_click_at
        ])

    output.seek(0)

    return StreamingResponse(iter([output.getvalue()]),
                             media_type="application/octet-stream",
                             headers={"Content-Disposition": "attachment; filename=links.csv"})


async def get_expired_links(session: AsyncSession,
                            user: User
                            ) -> ExpiredLinksResponse:
    """Получает все истекшие ссылки для текущего пользователя"""

    query = select(ExpiredLink).where(ExpiredLink.user_id == user.id)
    result = await session.execute(query)
    expired_links: List[ExpiredLink] = result.scalars().all()

    if not expired_links:
        raise HTTPException(
            status_code=404,
            detail="У вас нет истекших ссылок."
        )

    links = [ExpiredLinks.model_validate(link_data.__dict__) for link_data in expired_links]

    return ExpiredLinksResponse(links=links)


async def download_expired_links(session: AsyncSession,
                                 user: User
                                 ):
    """Возвращает csv-файл с информацией об истекших ссылках пользователя для скачивания"""

    query = select(ExpiredLink).where(ExpiredLink.user_id == user.id)
    result = await session.execute(query)
    expired_links: List[ExpiredLink] = result.scalars().all()

    if not expired_links:
        raise HTTPException(
            status_code=404,
            detail="У вас нет истекших ссылок."
        )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "Short Code", "Original URL", "Created At", "Expires At", "Clicks", "Last Click At"])

    for link_data in expired_links:
        writer.writerow([
            link_data.id,
            link_data.short_code,
            link_data.original_url,
            link_data.created_at,
            link_data.expires_at,
            link_data.clicks,
            link_data.last_click_at
        ])

    output.seek(0)

    return StreamingResponse(iter([output.getvalue()]),
                             media_type="application/octet-stream",
                             headers={"Content-Disposition": "attachment; filename=expired_links.csv"})


async def reactivate_link_by_id(reactivate_data: LinkReactivateRequest,
                                session: AsyncSession,
                                user: User) -> LinkReactivateResponse:
    """Возвращает истекшую ссылку в активные ссылки"""
    logging.info(f"Reactivating expired link {reactivate_data.id} for user {user.id}")

    query = select(ExpiredLink).where(ExpiredLink.id == reactivate_data.id, ExpiredLink.user_id == user.id)
    result = await session.execute(query)
    expired_link = result.scalar_one_or_none()

    if not expired_link:
        logging.error(f"Expired link {reactivate_data.id} not found")
        raise HTTPException(
            status_code=404,
            detail="Истекшая ссылка не найдена, проверьте корректность id."
        )

    if not reactivate_data.new_custom_alias:
        new_custom_alias = expired_link.short_code
        logging.info(f"Using original short code: {new_custom_alias}")

        conflict_query = select(Link).where(Link.short_code == new_custom_alias)
        conflict_result = await session.execute(conflict_query)

        if conflict_result.scalar_one_or_none():
            new_custom_alias = await get_unique_code(session)
            logging.info(f"Generated new short code: {new_custom_alias}")
    else:
        new_custom_alias = reactivate_data.new_custom_alias
        logging.info(f"Using new custom alias: {new_custom_alias}")
        conflict_query = select(Link).where(Link.short_code == new_custom_alias)
        conflict_result = await session.execute(conflict_query)

        if conflict_result.scalar_one_or_none():
            logging.error(f"New custom alias {new_custom_alias} already exists")
            raise HTTPException(
                status_code=400,
                detail="Алиас уже существует, выберите новый."
            )

    if not reactivate_data.new_expires_at:
        new_expires_at = datetime.utcnow() + timedelta(days=14)
        is_soft_expire = True
        logging.info(f"Setting soft expire: expires_at={new_expires_at}")
    else:
        new_expires_at = reactivate_data.new_expires_at
        is_soft_expire = False
        logging.info(f"Setting hard expire: expires_at={new_expires_at}")

    new_link = Link(
        original_url=expired_link.original_url,
        short_code=new_custom_alias,
        created_at=expired_link.created_at,
        expires_at=new_expires_at,
        is_soft_expire=is_soft_expire,
        user_id=expired_link.user_id,
        clicks=expired_link.clicks,
        last_click_at=expired_link.last_click_at
    )

    session.add(new_link)
    await session.delete(expired_link)
    await session.commit()
    logging.info(f"Link {expired_link.short_code} reactivated successfully as {new_custom_alias}")

    return LinkReactivateResponse(
        message="Ссылка успешно реактивирована",
        original_url=expired_link.original_url,
        short_code=new_custom_alias,
        expires_at=new_expires_at
    )
