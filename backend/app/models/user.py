from fastapi_users.db import SQLAlchemyBaseUserTable
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class User(SQLAlchemyBaseUserTable[int], TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
