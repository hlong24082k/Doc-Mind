import asyncio
import os
import sys

# Ensure server root and src are on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.dirname(CURRENT_DIR)
sys.path.insert(0, SERVER_DIR)

from app.db.init_db import init_db_async


if __name__ == "__main__":
    print("Running database initialization and seeding script...")
    asyncio.run(init_db_async())
    print("Database initialization and seed complete!")
