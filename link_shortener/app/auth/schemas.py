import uuid
from fastapi_users import schemas
from pydantic import ConfigDict

class UserRead(schemas.BaseUser[uuid.UUID]):
    model_config = ConfigDict(from_attributes=True)

class UserCreate(schemas.BaseUserCreate):
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(schemas.BaseUserUpdate):
    model_config = ConfigDict(from_attributes=True)