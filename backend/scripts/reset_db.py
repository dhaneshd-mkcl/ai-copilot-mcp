import os
import asyncio
import logging
import sys
from pathlib import Path

# Add backend directory to sys.path to import config
backend_dir = Path(__file__).parent.parent
sys.path.append(str(backend_dir))

try:
    import asyncpg
    import redis
    from config import config
except ImportError as e:
    print(f"Error: Missing dependencies. Please ensure you are in the correct environment. {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def reset_postgres():
    logger.info("Connecting to PostgreSQL...")
    dsn = config.PG_URL.replace("postgresql+asyncpg", "postgresql")
    try:
        conn = await asyncpg.connect(dsn)
        try:
            logger.info("Truncating 'embeddings' table...")
            await conn.execute("TRUNCATE TABLE embeddings")
            logger.info("PostgreSQL embeddings cleared successfully.")
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"PostgreSQL reset failed: {e}")

def reset_redis():
    logger.info("Connecting to Redis...")
    try:
        r = redis.from_url(config.REDIS_URL)
        r.ping()
        logger.info("Flushing Redis database...")
        r.flushdb()
        logger.info("Redis cleared successfully.")
    except Exception as e:
        logger.error(f"Redis reset failed: {e}")

async def main():
    print("=== Database Reset Utility ===")
    
    if config.USE_PGVECTOR:
        await reset_postgres()
    else:
        logger.info("PGVector is disabled in config.")

    if config.USE_REDIS:
        reset_redis()
    else:
        logger.info("Redis is disabled in config.")

    print("==============================")
    print("Reset complete.")

if __name__ == "__main__":
    asyncio.run(main())
