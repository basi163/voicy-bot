from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from config import settings
from database.models import Base

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migrations: add columns if they don't exist yet
        for migration in [
            "ALTER TABLE messages ADD COLUMN title VARCHAR(100)",
            "ALTER TABLE users ADD COLUMN is_unlimited BOOLEAN DEFAULT 0",
        ]:
            try:
                await conn.execute(text(migration))
            except Exception:
                pass  # column already exists


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
