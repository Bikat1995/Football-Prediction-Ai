import asyncio
import logging
import os
import sys
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from database.db import init_db

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def main():
    """Start the bot."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    
    if not token:
        logger.error("No TELEGRAM_BOT_TOKEN found in .env file. Please set it.")
        sys.exit(1)
        
    logger.info("Initializing Database...")
    await init_db()
        
    logger.info("Starting Football AI Prediction Bot...")
    
    # Initialize bot and dispatcher
    bot = Bot(token=token)
    dp = Dispatcher()

    # Include routers from handlers
    from handlers.registration import router as registration_router
    from handlers.menu import router as menu_router
    from handlers.competitions import router as competitions_router
    from handlers.predictions import router as predictions_router

    dp.include_router(registration_router)
    dp.include_router(menu_router)
    dp.include_router(competitions_router)
    dp.include_router(predictions_router)

    # Start polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())