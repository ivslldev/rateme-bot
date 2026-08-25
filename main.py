"""RateMe bot entry point."""
import asyncio
import logging
import os

from aiohttp import web
from aiogram import Bot, Dispatcher

import config
import db
from handlers import router


async def health(request):
    """Tiny endpoint so Render sees an open port and marks the deploy as Live."""
    return web.Response(text="OK")


async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    db.init_db()  # initialize SQLite on first launch
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Start a minimal HTTP server on Render's PORT so the platform
    # considers this service healthy and doesn't restart it.
    port = int(os.getenv("PORT", "8000"))
    app = web.Application()
    app.router.get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logging.info("Health-check server listening on port %s", port)

    await dp.start_polling(bot)


if __name__ == "__main__":
    if not config.BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN in .env (copy .env.example)")
    asyncio.run(main())
