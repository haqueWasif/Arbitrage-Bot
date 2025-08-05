import asyncio
import logging
import json
import websockets
from pybit.unified_trading import WebSocket as BybitWebSocket

logger = logging.getLogger(__name__)

class WebSocketManager:
    def __init__(self, config):
        self.config = config
        self.exchanges_config = config["EXCHANGES"]
        self.trade_symbols = config["TRADING_CONFIG"]["trade_symbols"]
        self.market_data = {}
        self.lock = asyncio.Lock()
        self.bybit_ws = None

    async def start(self):
        """Start Binance & Bybit WebSocket connections."""
        await asyncio.gather(
            self._run_binance_stream(),
            self._run_bybit_streams(),
        )
        logger.info("WebSocket Manager started for Binance and Bybit.")

    # -------------------- BINANCE --------------------
    async def _run_binance_stream(self):
        """Connect to Binance multi-stream WebSocket for all symbols."""
        streams = [f"{s.lower()}@ticker" for s in self.trade_symbols]
        stream_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"

        while True:
            try:
                logger.info(f"Connecting to Binance WS for symbols: {self.trade_symbols}")
                async with websockets.connect(
                    stream_url,
                    open_timeout=30,    # increase handshake timeout
                    ping_interval=20,
                    ping_timeout=20
                ) as ws:
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        
                        # Binance multi-stream returns {"stream": "...", "data": {...}}
                        stream_name = data.get("stream", "")
                        payload = data.get("data", {})

                        if stream_name and payload:
                            symbol = payload.get("s")  # Binance ticker symbol (e.g., BTCUSDT)
                            if symbol:
                                async with self.lock:
                                    self.market_data.setdefault("binance", {})[symbol] = payload
                                logger.debug(f"Binance update for {symbol}: {payload}")

            except Exception as e:
                logger.error(f"Binance WS error: {repr(e)}", exc_info=True)
                await asyncio.sleep(5)  # retry after short delay

    # -------------------- BYBIT --------------------
    async def _run_bybit_streams(self):
        """Connect to Bybit WebSocket for all symbols."""
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
                loop.call_soon_threadsafe(
                    asyncio.create_task,
                    self._bybit_update("bybit", symbol, msg)
                )
            return callback

        for symbol in self.trade_symbols:
            self.bybit_ws.trade_stream(callback=make_callback(symbol), symbol=symbol)

        while True:
            await asyncio.sleep(3600)

    async def _bybit_update(self, exchange_id, symbol, data):
        async with self.lock:
            self.market_data.setdefault(exchange_id, {})[symbol] = data
        logger.debug(f"Bybit update: {symbol} {data}")

    # -------------------- UTILITIES --------------------
    async def get_latest_market_data(self, exchange_id, symbol):
        async with self.lock:
            return self.market_data.get(exchange_id, {}).get(symbol, None)

    async def stop(self):
        logger.info("Stopping WebSocket Manager...")
        self.bybit_ws = None
