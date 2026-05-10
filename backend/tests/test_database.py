from sqlalchemy import text

from app.database import get_async_session


async def test_database_session_executes_query():
    async for session in get_async_session():
        result = await session.execute(text("SELECT 1"))
        value = result.scalar_one()
        assert value == 1
        break
