from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, Field


# Создание short code
class LinkCreateRequest(BaseModel):
    original_url: HttpUrl
    custom_alias: Optional[str] = Field(default=None, max_length=20)
    expires_at: Optional[datetime] = None


class LinkCreateResponse(BaseModel):
    message: str
    original_url: str
    short_code: str
    expires_at: Optional[datetime]


# Обновление short code
class LinkUpdateRequest(BaseModel):
    short_code: str
    new_short_code: Optional[str] = Field(default=None, max_length=20)


class LinkUpdateResponse(BaseModel):
    message: str
    original_url: str
    short_code: str


# Статистика ссылки
class LinkStatsResponse(BaseModel):
    original_url: str
    short_code: str
    created_at: datetime
    last_click_at: Optional[datetime]
    clicks: int

    class Config:
        model_config = {'from_attributes': True}


# Возврат short code по URL
class LinkSearch(BaseModel):
    original_url: str
    short_code: str

    class Config:
        model_config = {'from_attributes': True}


class LinkSearchResponse(BaseModel):
    links: List[LinkSearch]


# Возврат всех ссылок юзера
class UsersLinks(BaseModel):
    short_code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    clicks: int
    last_click_at: Optional[datetime]

    class Config:
        model_config = {'from_attributes': True}


class UsersLinksResponse(BaseModel):
    links: List[UsersLinks]


# Возврат иcтекших ссылок юзера
class ExpiredLinks(BaseModel):
    id: int
    original_url: str
    short_code: str
    created_at: datetime
    expires_at: datetime
    last_click_at: datetime | None
    clicks: int

    class Config:
        model_config = {'from_attributes': True}


class ExpiredLinksResponse(BaseModel):
    links: List[ExpiredLinks]

# Реактивация истекших ссылок юзера
class LinkReactivateRequest(BaseModel):
    id: int
    new_custom_alias: Optional[str] = Field(default=None, max_length=20)
    new_expires_at: Optional[datetime] = None


class LinkReactivateResponse(BaseModel):
    message: str
    original_url: str
    short_code: str
    expires_at: Optional[datetime]