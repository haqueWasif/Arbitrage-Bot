"""
Price Monitoring System for detecting arbitrage opportunities in real-time.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
import statistics

from exchange_manager import ExchangeManager, ArbitrageOpportunity
from config import TRADING_CONFIG, PERFORMANCE_CONFIG

logger = logging.getLogger(__name__)

@dataclass
class PriceAlert:
    """Represents a price alert or anomaly."""
    exchange: str
    symbol: str
    alert_type: str  # 'spike', 'drop', 'stale_data', 'spread_anomaly'
    current_price: float
    reference_price: Optional[float]
    deviation_pct: float
    timestamp: float
    message: str

@dataclass
class MarketStats:
    """Market statistics for a trading pair."""
    symbol: str
    exchanges: List[str] = field(default_factory=list)
    prices: Dict[str, float] = field(default_factory=dict)
    spreads: Dict[str, float] = field(default_factory=dict)  # bid-ask spread per exchange
    price_history: Dict[str, deque] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=100)))
    last_update: Dict[str, float] = field(default_factory=dict)
    
    def add_price_data(self, exchange: str, bid: float, ask: float, timestamp: float):
        """Add new price data for an exchange."""
        mid_price = (bid + ask) / 2
        spread = ask - bid
        
        self.prices[exchange] = mid_price
        self.spreads[exchange] = spread
        self.price_history[exchange].append((timestamp, mid_price))
        self.last_update[exchange] = timestamp
        
        if exchange not in self.exchanges:
            self.exchanges.append(exchange)
    
    def get_price_volatility(self, exchange: str, window_minutes: int = 5) -> Optional[float]:
        """Calculate price volatility over a time window."""
        if exchange not in self.price_history:
            return None
        
        current_time = time.time()
        cutoff_time = current_time - (window_minutes * 60)
        
        # Get recent prices
        recent_prices = [
            price for timestamp, price in self.price_history[exchange]
            if timestamp >= cutoff_time
        ]
        
        if len(recent_prices) < 2:
            return None
        
        # Calculate standard deviation as volatility measure
        return statistics.stdev(recent_prices)
    
    def get_cross_exchange_spread(self) -> Optional[float]:
        """Calculate the spread between highest and lowest prices across exchanges."""
        if len(self.prices) < 2:
            return None
        
        prices = list(self.prices.values())
        return max(prices) - min(prices)

    
class PriceMonitor:
    def __init__(self, exchange_manager: ExchangeManager, monitoring_system: Any, performance_config: Dict[str, Any]): # <--- MODIFIED LINE
        self.exchange_manager = exchange_manager
        self.monitoring_system = monitoring_system
        self.performance_config = performance_config
        self.tickers: Dict[str, Dict[str, Any]] = {}
        self.order_books: Dict[str, Dict[str, Any]] = {}
        self.opportunities: deque[ArbitrageOpportunity] = deque(maxlen=100)
        self.last_scan_time = time.time()

    async def start_monitoring(self):
        logger.info("Starting price monitoring...")
        while True:
            try:
                await self._scan_for_opportunities()
            except Exception as e:
                logger.error(f"Error in price monitoring loop: {e}")
                self.monitoring_system.alert_manager.create_alert(
                    "Price Monitor Error", f"Error in price monitoring loop: {e}", "error", "PriceMonitor"
                )
            await asyncio.sleep(self.performance_config.get("price_update_interval", 0.1))

    async def _scan_for_opportunities(self):
        # Fetch tickers from all configured exchanges
        tasks = []
        for exchange_id in self.exchange_manager.exchanges_config.keys():
            for symbol in ["BTC/USDT", "ETH/USDT"]: # Example symbols, expand as needed
                tasks.append(self.exchange_manager.fetch_ticker(exchange_id, symbol))
        
        tickers_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Update internal ticker cache
        # Reset tickers for this scan to ensure fresh data
        self.tickers = {}
        
        idx = 0
        for exchange_id in self.exchange_manager.exchanges_config.keys():
            for symbol in ["BTC/USDT", "ETH/USDT"]:
                ticker = tickers_results[idx]
                if not isinstance(ticker, Exception) and ticker is not None:
                    if exchange_id not in self.tickers:
                        self.tickers[exchange_id] = {}
                    self.tickers[exchange_id][symbol] = ticker
                else:
                    logger.warning(f"Could not fetch valid ticker for {symbol} on {exchange_id}: {ticker}")
                idx += 1

        # Find arbitrage opportunities
        self.opportunities.clear() # Clear old opportunities
        opportunities_found_total = 0

        for symbol in ["BTC/USDT", "ETH/USDT"]:
            for buy_exchange_id, buy_exchange_tickers in self.tickers.items():
                if symbol not in buy_exchange_tickers or not buy_exchange_tickers[symbol]:
                    continue
                
                buy_price = buy_exchange_tickers[symbol].get("ask")
                
                # Ensure buy_price is not None and is a valid number
                if buy_price is None or not isinstance(buy_price, (int, float)) or buy_price <= 0:
                    continue

                for sell_exchange_id, sell_exchange_tickers in self.tickers.items():
                    if buy_exchange_id == sell_exchange_id:
                        continue
                    if symbol not in sell_exchange_tickers or not sell_exchange_tickers[symbol]:
                        continue
                    
                    sell_price = sell_exchange_tickers[symbol].get("bid")

                    # Ensure sell_price is not None and is a valid number
                    if sell_price is None or not isinstance(sell_price, (int, float)) or sell_price <= 0:
                        continue

                    # Calculate potential profit (simplified, without fees)
                    if sell_price > buy_price: # Only consider if sell price is higher than buy price
                        potential_profit_pct = ((sell_price - buy_price) / buy_price) * 100
                        
                        # Apply minimum profit threshold from config
                        # Ensure self.monitoring_system.config is accessible and has TRADING_CONFIG
                        min_profit_threshold = self.monitoring_system.config.get("TRADING_CONFIG", {}).get("min_profit_threshold", 0.001)

                        if potential_profit_pct > min_profit_threshold * 100:
                            # Placeholder for max_quantity calculation (e.g., based on available balance, order book depth)
                            # Calculate max_quantity based on a percentage of available capital
                            # For simplicity, assuming available capital is represented by the MAX_TRADE_AMOUNT_USD for now
                            # In a real scenario, this would involve fetching actual exchange balances.
                            trade_percentage = 0.01 # Example: 1% of capital per trade
                            max_quantity = max(0.001, (TRADING_CONFIG.get("max_trade_amount_usd") * trade_percentage) / buy_price)
                            potential_profit_usd = (sell_price - buy_price) * max_quantity
                            opportunity = ArbitrageOpportunity(
                                symbol=symbol,
                                buy_exchange=buy_exchange_id,
                                sell_exchange=sell_exchange_id,
                                buy_price=buy_price,
                                sell_price=sell_price,
                                potential_profit_pct=potential_profit_pct,
                                potential_profit_usd=potential_profit_usd,
                                max_quantity=max_quantity,
                                timestamp=time.time()
                            )
                            self.opportunities.append(opportunity)
                            opportunities_found_total += 1
            
            if opportunities_found_total > 0:
                logger.info(f"Found {opportunities_found_total} arbitrage opportunities for {symbol}.")

        self.last_scan_time = time.time()
        self.monitoring_system.update_performance_metrics(
            active_trades_count=0, # This should come from trading_engine
            opportunities_found=opportunities_found_total,
            trade_execution_times=[] # This should come from trading_engine
        )


    def get_arbitrage_opportunities(self) -> List[ArbitrageOpportunity]:
        return list(self.opportunities)

    def get_market_summary(self) -> Dict[str, Any]:
        summary = {"tickers": self.tickers, "last_scan": self.last_scan_time}
        return summary