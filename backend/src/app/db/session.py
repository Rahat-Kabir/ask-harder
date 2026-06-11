from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine = create_async_engine(settings.database_url)

# expire_on_commit=False: after commit, objects keep their loaded values
# instead of triggering implicit refresh queries — those break under asyncio.
new_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request."""
    async with new_session() as session:
        yield session
