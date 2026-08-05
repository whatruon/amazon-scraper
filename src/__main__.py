"""Entry point for `python -m src` (the Apify Dockerfile CMD)."""
import asyncio

from .main import main

if __name__ == "__main__":
    asyncio.run(main())
