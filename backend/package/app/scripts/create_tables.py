import asyncio

from app.database import client, initialize_database


async def create_tables() -> None:
    await initialize_database()


async def run() -> None:
    try:
        await create_tables()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run())