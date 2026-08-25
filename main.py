"""RateMe bot entry point."""
import asyncio
import logging

from aiogram import Bot, Dispatcher

import config
import db
from handlers import router


async def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    db.init_db()  # initialize SQLite on first launch
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    if not config.BOT_TOKEN:
        raise SystemExit("Set BOT_TOKEN in .env (copy .env.example)")
    asyncio.run(main())