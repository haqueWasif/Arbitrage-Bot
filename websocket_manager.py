import asyncio
import logging
import aiohttp
from binance import AsyncClient, BinanceSocketManager
from pybit.unified_trading import WebSocket as BybitWebSocket

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self, config):
        self.config = config
        self.exchanges_config = config["EXCHANGES"]
        self.trade_symbols = config["TRADING_CONFIG"]["trade_symbols"]
        self.market_data = {}
        self.lock = asyncio.Lock()
        self.binance_client = None
        self.binance_bsm = None
        self.bybit_ws = None
        self.bybit_tasks = []

    async def start(self):
        await asyncio.gather(
            self._run_binance_loop(),
            self._run_bybit_streams(),
        )
        logger.info("WebSocket Manager started for Binance and Bybit.")

    async def _run_binance_loop(self):
        exchange_config = self.exchanges_config.get("binance", {})
        api_key = exchange_config.get("api_key")
        api_secret = exchange_config.get("secret")
        sandbox = exchange_config.get("sandbox", False)
    
        while True:
            try:
                logger.info("Connecting to Binance websocket (testnet=%s)...", sandbox)
                self.binance_client = await AsyncClient.create(api_key, api_secret, testnet=sandbox)
                self.binance_bsm = BinanceSocketManager(self.binance_client)
                socket_tasks = [
                    asyncio.create_task(self._binance_listen(symbol))
                    for symbol in self.trade_symbols
                ]
                await asyncio.gather(*socket_tasks)
            except asyncio.TimeoutError:
                logger.error("Binance API connection timed out. Retrying in 5 seconds...")
            except Exception as e:
                logger.error(f"Binance websocket error: {repr(e)}", exc_info=True)
            finally:
                if self.binance_client:
                    await self.binance_client.close_connection()
                self.binance_client = None
                self.binance_bsm = None
                await asyncio.sleep(5)


    async def _binance_listen(self, symbol):
        try:
            socket = self.binance_bsm.symbol_ticker_socket(symbol.lower())
            async with socket as s:
                while True:
                    msg = await s.recv()
                    if isinstance(msg, dict) and msg.get('e') == 'error':
                        logger.error(f"Binance websocket stream error for {symbol}: {msg}")
                        break  # Will escape the socket context and reconnect
                    async with self.lock:
                        self.market_data.setdefault("binance", {})[symbol] = msg
                    logger.debug(f"Binance update for {symbol}: {msg}")
        except Exception as e:
            logger.error("Binance socket for %s error: %r", symbol, e, exc_info=True)


    async def _run_bybit_streams(self):
        exchange_config = self.exchanges_config.get("bybit", {})
        api_key = exchange_config.get("api_key")
        api_secret = exchange_config.get("secret")
        sandbox = exchange_config.get("sandbox", False)

        logger.info("Connecting to Bybit WebSocket (testnet=%s)...", sandbox)
        self.bybit_ws = BybitWebSocket(
            testnet=sandbox,
            channel_type="spot",
            api_key=api_key,
            api_secret=api_secret
        )

        loop = asyncio.get_running_loop()

        def make_callback(symbol):
            def callback(msg):
                # Schedule async callback from this thread-safe callback
                loop.call_soon_threadsafe(
                    asyncio.create_task,
                    self._bybit_update("bybit", symbol, msg)
                )
            return callback

        # Subscribe to trades for all symbols
        for symbol in self.trade_symbols:
            self.bybit_ws.trade_stream(callback=make_callback(symbol), symbol=symbol)

        # pybit handles keep-alive internally; just keep this task alive
        while True:
            await asyncio.sleep(3600)

    async def _bybit_update(self, exchange_id, symbol, data):
        async with self.lock:
            self.market_data.setdefault(exchange_id, {})[symbol] = data
        logger.debug(f"Bybit update: {symbol} {data}")

    async def get_latest_market_data(self, exchange_id, symbol):
        async with self.lock:
            return self.market_data.get(exchange_id, {}).get(symbol, None)

    async def stop(self):
        if self.binance_client:
            await self.binance_client.close_connection()
            logger.info("Binance client connection closed.")
        if self.bybit_ws:
            # No manual exit needed for pybit unified_trading
            self.bybit_ws = None
            logger.info("Bybit WebSocket client reference cleared.")
        logger.info("WebSocket Manager stopped.")
