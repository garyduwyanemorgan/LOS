"""Generic async repository providing standard CRUD operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

from sqlalchemy import func, select, update

from backend.core.exceptions.exceptions import ResourceNotFoundException
from backend.database.connection import Base

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Generic repository for async SQLAlchemy ORM models.

    Provides standard CRUD operations.  All methods operate within the
    provided AsyncSession; transaction management is the caller's responsibility.

    Usage::

        repo = BaseRepository(Lagoon, session)
        lagoon = await repo.get_by_id(lagoon_id)
    """

    def __init__(self, model: type[T], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> T | None:
        """Fetch a single record by primary key.

        Returns None if not found (does not raise).
        """
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def get_by_id_or_raise(self, id: uuid.UUID) -> T:
        """Fetch a single record by primary key.

        Raises:
            ResourceNotFoundException: if the record does not exist.
        """
        obj = await self.get_by_id(id)
        if obj is None:
            raise ResourceNotFoundException(
                resource_type=self.model.__name__,
                resource_id=str(id),
            )
        return obj

    async def list(
        self,
        filters: dict[str, Any] | None = None,
        skip: int = 0,
        limit: int = 100,
        order_by: str | None = None,
        order_desc: bool = True,
    ) -> list[T]:
        """Fetch a paginated, filtered list of records.

        Args:
            filters: Simple equality filters as column → value pairs.
            skip: Number of records to skip (offset).
            limit: Maximum number of records to return.
            order_by: Column name to order by.  Defaults to 'created_at' if present.
            order_desc: Whether to sort descending.
        """
        stmt = select(self.model)

        if filters:
            for column_name, value in filters.items():
                column = getattr(self.model, column_name, None)
                if column is not None and value is not None:
                    stmt = stmt.where(column == value)

        # Apply ordering
        if order_by:
            order_col = getattr(self.model, order_by, None)
            if order_col is not None:
                stmt = stmt.order_by(order_col.desc() if order_desc else order_col.asc())
        elif hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc() if order_desc else self.model.created_at.asc())  # type: ignore[attr-defined]

        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> T:
        """Create a new record from a dictionary of field values.

        Returns the created instance (with id and timestamps populated).
        """
        obj = self.model(**data)  # type: ignore[call-arg]
        self.session.add(obj)
        await self.session.flush()  # obtain id without committing
        await self.session.refresh(obj)
        return obj

    async def update(self, id: uuid.UUID, data: dict[str, Any]) -> T | None:
        """Update fields of an existing record.

        Returns the updated instance, or None if not found.
        """
        obj = await self.get_by_id(id)
        if obj is None:
            return None

        # Remove keys not present on the model to avoid attribute errors.
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)

        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update_or_raise(self, id: uuid.UUID, data: dict[str, Any]) -> T:
        """Update fields of an existing record.

        Raises:
            ResourceNotFoundException: if the record does not exist.
        """
        result = await self.update(id, data)
        if result is None:
            raise ResourceNotFoundException(
                resource_type=self.model.__name__,
                resource_id=str(id),
            )
        return result

    async def soft_delete(self, id: uuid.UUID) -> bool:
        """Set is_active=False on a record (soft delete).

        Returns True if the record was found and deactivated, False otherwise.
        Raises AttributeError if the model has no is_active column.
        """
        if not hasattr(self.model, "is_active"):
            raise AttributeError(
                f"Model {self.model.__name__} does not support soft delete "
                f"(no 'is_active' column)."
            )

        result = await self.session.execute(
            update(self.model)
            .where(self.model.id == id)  # type: ignore[attr-defined]
            .values(is_active=False)
            .returning(self.model.id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none() is not None

    async def hard_delete(self, id: uuid.UUID) -> bool:
        """Permanently delete a record.

        Use with caution.  Prefer soft_delete for most tables.
        Returns True if a row was deleted.
        """
        obj = await self.get_by_id(id)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.flush()
        return True

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count records matching the given equality filters."""
        stmt = select(func.count()).select_from(self.model)

        if filters:
            for column_name, value in filters.items():
                column = getattr(self.model, column_name, None)
                if column is not None and value is not None:
                    stmt = stmt.where(column == value)

        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: uuid.UUID) -> bool:
        """Return True if a record with the given id exists."""
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(
                self.model.id == id  # type: ignore[attr-defined]
            )
        )
        return result.scalar_one() > 0

    async def bulk_create(self, data_list: list[dict[str, Any]]) -> list[T]:
        """Create multiple records in a single flush."""
        objects = [self.model(**data) for data in data_list]  # type: ignore[call-arg]
        self.session.add_all(objects)
        await self.session.flush()
        for obj in objects:
            await self.session.refresh(obj)
        return objects
