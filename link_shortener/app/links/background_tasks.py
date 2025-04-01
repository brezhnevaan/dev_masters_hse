import asyncio
import logging
from datetime import datetime
from sqlalchemy import delete, select, insert
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from app.database.database import async_session_maker

from app.links.models import Link, ExpiredLink
from app.links.service import delete_link_from_cache

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s",
                    handlers=[logging.StreamHandler()])


async def delete_expired_links(session: AsyncSession):
    """Перемещает истекшие ссылки авторизованных пользователей в таблицу expired_links
    и удаляет их из основной таблицы. Ссылки неавторизованных пользователей просто удаляет """

    logging.info("Starting expired links cleanup")
    now = datetime.utcnow()
    query = select(Link).where(Link.expires_at.is_not(None), Link.expires_at < now)
    result = await session.execute(query)
    expired_links = result.scalars().all()

    if expired_links:
        logging.info(f"Found {len(expired_links)} expired links")
        for link in expired_links:
            # Операции с истекшими ссылками доступны только авторизованным пользователям
            # Если у ссылки есть user_id, перемещаем её в таблицу expired_links
            if link.user_id:
                logging.info(f"Moving expired link {link.short_code} to expired_links table for user {link.user_id}")
                expired_link = ExpiredLink(
                    user_id=link.user_id,
                    original_url=link.original_url,
                    short_code=link.short_code,
                    created_at=link.created_at,
                    expires_at=link.expires_at,
                    last_click_at=link.last_click_at,
                    clicks=link.clicks
                )
                session.add(expired_link)
            else:
                logging.info(f"Deleting expired link {link.short_code} (no user_id)")

            await session.delete(link)
            await delete_link_from_cache(link.short_code)

        await session.commit()
        logging.info(f"Successfully processed {len(expired_links)} expired links")
    else:
        logging.info("No expired links found")


async def cleanup_expired_links():
    """Запускает очистку истекших ссылок каждыe 10 минут"""
    logging.info("Starting expired links cleanup task")
    while True:
        async with async_session_maker() as session:
            await delete_expired_links(session)
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(app):
    """Запускает фоновые задачи при старте приложения"""
    logging.info("Starting background tasks")
    cleanup_task = asyncio.create_task(cleanup_expired_links())
    yield
    logging.info("Stopping background tasks")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        logging.info("Cleanup task cancelled successfully")


async def main():
    """Основная функция для запуска фоновых задач"""
    logging.info("Starting background tasks worker")
    await cleanup_expired_links()

if __name__ == "__main__":
    asyncio.run(main())