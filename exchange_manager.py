import ccxt
import asyncio
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

@dataclass
class ArbitrageOpportunity:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    potential_profit_pct: float
    potential_profit_usd: float
    max_quantity: float
    timestamp: float





class ExchangeManager:
    def __init__(self, exchanges_config: Dict[str, Any]):
        self.exchanges_config = exchanges_config
        self.exchanges: Dict[str, Any] = {}
        self.initialized = False

    async def initialize_exchanges(self):
        if self.initialized:
            logger.info("Exchanges already initialized.")
            return

        logger.info("Initializing exchanges...")
        for exchange_id, config in self.exchanges_config.items():
            try:
                logger.info(f"Attempting to initialize {exchange_id}...")
                
                # Skip exchanges with missing API credentials
                if not config.get("api_key") or not config.get("secret"):
                    logger.warning(f"Skipping {exchange_id}: Missing API credentials")
                    continue
                
                exchange_class = getattr(ccxt, exchange_id)
                
                # Base configuration for all exchanges
                exchange_config = {
                    "apiKey": config["api_key"],
                    "secret": config["secret"],
                    "enableRateLimit": True,
                    "options": {
                        "defaultType": "spot",  # Ensure we use spot trading
                        "adjustForTimeDifference": True,
                    }
                }
                
                # Add passphrase for exchanges that require it (like Coinbase Pro)
                if config.get("passphrase"):
                    exchange_config["password"] = config["passphrase"]
                
                # Create exchange instance
                exchange = exchange_class(exchange_config)
                
                # Set sandbox mode if specified and supported
                if config.get("sandbox", False):
                    try:
                        exchange.set_sandbox_mode(True)
                        logger.info(f"Set {exchange_id} to SANDBOX mode.")
                    except Exception as sandbox_error:
                        logger.warning(f"Sandbox mode not supported for {exchange_id}: {sandbox_error}")
                        logger.info(f"Continuing with {exchange_id} in LIVE mode.")
                else:
                    logger.info(f"Set {exchange_id} to LIVE mode.")

                # Load markets (handle both sync and async cases)
                logger.info(f"Loading markets for {exchange_id}...")
                try:
                    # Try async first
                    markets = await exchange.load_markets()
                except TypeError:
                    # If TypeError (can\"t await), try sync
                    markets = exchange.load_markets()
                
                logger.info(f"Successfully loaded {len(markets)} markets for {exchange_id}")
                
                # Store the initialized exchange
                self.exchanges[exchange_id] = exchange
                logger.info(f"Successfully initialized {exchange_id}. Current exchanges: {list(self.exchanges.keys())}")
                
            except Exception as e:
                logger.error(f"Failed to initialize exchange {exchange_id}: {type(e).__name__}: {str(e)}")
                # Continue with other exchanges even if one fails
                continue
        
        self.initialized = True
        logger.info(f"Exchange initialization complete. Successfully initialized: {list(self.exchanges.keys())}")

    async def fetch_ticker(self, exchange_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        exchange = self.exchanges.get(exchange_id)
        if not exchange:
            logger.warning(f"Exchange {exchange_id} not initialized.")
            return None
        try:
            # Try async first
            ticker = await exchange.fetch_ticker(symbol)
        except TypeError:
            # If TypeError (can\"t await), try sync
            ticker = exchange.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Failed to fetch ticker for {symbol} on {exchange_id}: {e}")
            return None
        return ticker

    async def place_order(self, exchange_id: str, symbol: str, order_type: str, side: str, amount: float, price: Optional[float] = None) -> Optional[Dict[str, Any]]:
        exchange = self.exchanges.get(exchange_id)
        if not exchange:
            logger.warning(f"Exchange {exchange_id} not initialized.")
            return None

        logger.info(f"DEBUG: place_order called with order_type={order_type}, side={side}")
        order = None
        try:
            # Check for notional filter (minimum order value)
            if 'limits' in exchange.markets[symbol] and 'notional' in exchange.markets[symbol]['limits']:
                min_notional = exchange.markets[symbol]['limits']['notional']['min']
                if price and (amount * price) < min_notional:
                    logger.warning(f"Adjusting amount for {symbol} on {exchange_id} to meet min notional value. Original amount: {amount}, Price: {price}, Min Notional: {min_notional}")
                    amount = min_notional / price
                    logger.warning(f"New adjusted amount: {amount}")

            if order_type == "limit":
                if side == "buy":
                    order_creation_method = exchange.create_limit_buy_order
                elif side == "sell":
                    order_creation_method = exchange.create_limit_sell_order
                else:
                    logger.error(f"Unsupported side for limit order: {side}")
                    return None
                args = (symbol, amount, price)
            elif order_type == "market":
                if side == "buy":
                    order_creation_method = exchange.create_market_buy_order
                elif side == "sell":
                    order_creation_method = exchange.create_market_sell_order
                else:
                    logger.error(f"Unsupported side for market order: {side}")
                    return None
                args = (symbol, amount)
            else:
                logger.error(f"Unsupported order type received: {order_type}. Expected \'limit\' or \'market\'.")
                return None

            # Directly call the order creation method without await initially
            # This handles cases where the method might return a dict directly (e.g., testnets)
            order = order_creation_method(*args)

            # If the result is an awaitable, then await it
            if asyncio.iscoroutine(order):
                order = await order
            
            logger.info(f"DEBUG: Type of order after call: {type(order)}")

        except Exception as e:
            logger.error(f"Failed to place {side} {order_type} order for {amount} {symbol} on {exchange_id}: {e}")
            return None
        
        logger.info(f"Placed {side} {order_type} order {order.get('id', 'N/A')} for {amount} {symbol} on {exchange_id}.")
        return order

    async def get_balance(self, exchange_id: str, currency: str) -> float:
        exchange = self.exchanges.get(exchange_id)
        if not exchange:
            logger.warning(f"Exchange {exchange_id} not initialized.")
            return 0.0
        try:
            balance = exchange.fetch_balance()

            return balance["free"].get(currency, 0.0)
        except Exception as e:
            logger.error(f"Failed to fetch balance for {currency} on {exchange_id}: {e}")
            return 0.0

    async def get_all_balances(self) -> Dict[str, Dict[str, float]]:
        all_balances = {}
        for exchange_id, exchange in self.exchanges.items():
            try:
                balance = exchange.fetch_balance()
                if asyncio.iscoroutine(balance):
                    balance = await balance
            except Exception as e:
                logger.error(f"Failed to fetch all balances for {exchange_id}: {e}")
                all_balances[exchange_id] = {"error": str(e)}
                continue # Continue to next exchange if this one fails

            all_balances[exchange_id] = {
                "free": balance["free"],
                "used": balance["used"],
                "total": balance["total"]
            }
        return all_balances

    async def get_order_book(self, exchange_id: str, symbol: str, limit: int = 10) -> Optional[Dict[str, Any]]:
        exchange = self.exchanges.get(exchange_id)
        if not exchange:
            logger.warning(f"Exchange {exchange_id} not initialized.")
            return None
        try:
            order_book = await exchange.fetch_order_book(symbol, limit=limit)
        except TypeError:
            order_book = exchange.fetch_order_book(symbol, limit=limit)
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol} on {exchange_id}: {e}")
            return None
        return order_book

    async def close(self):
        logger.info("Closing exchange connections...")
        for exchange_id, exchange in self.exchanges.items():
            try:
                # Some exchanges might have a close method, others might not
                if hasattr(exchange, "close"):
                    await exchange.close()
                logger.info(f"Closed connection for {exchange_id}.")
            except Exception as e:
                logger.error(f"Error closing connection for {exchange_id}: {e}")
                
    def get_exchange_trading_fee(self, exchange_id: str) -> float:
        """Returns the configured trading fee for a given exchange."""
        config = self.exchanges_config.get(exchange_id)
        if config and "trading_fee" in config:
            return config["trading_fee"]
        logger.warning(f"Trading fee not found for {exchange_id}. Returning default 0.001.")
        return 0.001