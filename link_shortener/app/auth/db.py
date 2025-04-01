from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.base import Base
from app.database.database import engine, get_async_session
from app.links.models import Link, ExpiredLink

class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "user"
    
    links = relationship("Link", back_populates="user")
    expired_links = relationship("ExpiredLink", back_populates="user")

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_users_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)