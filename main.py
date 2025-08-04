"""
Main entry point for the Crypto Arbitrage Bot.
This script runs the bot as a standalone application.
"""

import asyncio
import signal
import sys
import logging

from arbitrage_bot import ArbitrageBot
from config import load_config
from websocket_manager import WebSocketManager

logger = logging.getLogger(__name__)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}. Initiating shutdown...")
    # Set the shutdown event if bot is running
    if hasattr(signal_handler, 'bot') and signal_handler.bot:
        signal_handler.bot.shutdown_event.set()

async def main():
    """Main function to run the arbitrage bot."""
    try:
        # Load configuration
        config = load_config()
        
        # Create bot instance
        bot = ArbitrageBot(config)

        # Initialize WebSocket Manager
        websocket_manager = WebSocketManager(config)
        bot.set_websocket_manager(websocket_manager)
        
        # Store bot reference for signal handler
        signal_handler.bot = bot
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("Starting Crypto Arbitrage Bot...")
        
        # Run the bot
        await bot.run_forever()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt. Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
        sys.exit(1)
    finally:
        logger.info("Bot shutdown complete.")

if __name__ == "__main__":
    # This ensures the bot only runs when this script is executed directly
    # and not when it's imported by other modules (like the dashboard)
    asyncio.run(main())