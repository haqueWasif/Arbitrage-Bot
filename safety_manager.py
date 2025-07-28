"""
Safety Manager - Comprehensive safety features to prevent losses in the arbitrage bot.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import json

from config import RISK_CONFIG, TRADING_CONFIG
from trading_engine import ArbitrageTrade, TradeStatus
from exchange_manager import ArbitrageOpportunity
from error_handler import ErrorHandler, ErrorCategory, ErrorSeverity

logger = logging.getLogger(__name__)

class SafetyLevel(Enum):
    """Safety alert levels."""
    GREEN = 1    # Normal operation
    YELLOW = 2   # Caution - increased monitoring
    ORANGE = 3   # Warning - restricted operation
    RED = 4      # Critical - emergency stop

class SafetyRule(Enum):
    """Types of safety rules."""
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    SINGLE_TRADE_LOSS = "single_trade_loss"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    BALANCE_THRESHOLD = "balance_threshold"
    PRICE_DEVIATION = "price_deviation"
    VOLUME_ANOMALY = "volume_anomaly"
    API_ERROR_RATE = "api_error_rate"
    EXECUTION_TIME = "execution_time"
    SPREAD_ANOMALY = "spread_anomaly"
    MARKET_VOLATILITY = "market_volatility"

@dataclass
class SafetyViolation:
    """Represents a safety rule violation."""
    rule: SafetyRule
    severity: SafetyLevel
    message: str
    current_value: float
    threshold_value: float
    timestamp: float
    component: str
    context: Dict[str, Any]

@dataclass
class SafetyMetrics:
    """Current safety metrics."""
    daily_pnl: float = 0.0
    consecutive_losses: int = 0
    last_trade_loss: float = 0.0
    api_error_rate: float = 0.0
    avg_execution_time: float = 0.0
    max_price_deviation: float = 0.0
    total_trades_today: int = 0
    emergency_stops_triggered: int = 0
    last_balance_check: float = 0.0
    balance_warnings: int = 0

class SafetyManager:
    def __init__(self, monitoring_system: Any, risk_config: Dict[str, Any]): # <--- MODIFIED LINE
        self.monitoring_system = monitoring_system
        self.risk_config = risk_config
        self.daily_profit_loss = 0.0
        self.consecutive_losses = 0
        self.circuit_breaker_active = False
        self.last_trade_time = None
        self.initial_balances: Dict[str, Dict[str, float]] = {}

    async def initialize_balances(self, exchange_manager: Any):
        logger.info("Initializing safety manager with current balances...")
        self.initial_balances = await exchange_manager.get_all_balances()
        logger.info(f"Initial balances: {self.initial_balances}")

    def record_profit(self, profit_usd: float):
        self.daily_profit_loss += profit_usd
        self.consecutive_losses = 0
        self.last_trade_time = time.time()
        logger.info(f"Recorded profit: ${profit_usd:.2f}. Daily P/L: ${self.daily_profit_loss:.2f}")
        self.monitoring_system.alert_manager.create_alert(
            "Profit Recorded", f"Trade resulted in profit: ${profit_usd:.2f}", "info", "SafetyManager"
        )

    def record_loss(self, loss_usd: float):
        self.daily_profit_loss -= abs(loss_usd) # Ensure loss is negative
        self.consecutive_losses += 1
        self.last_trade_time = time.time()
        logger.warning(f"Recorded loss: ${loss_usd:.2f}. Daily P/L: ${self.daily_profit_loss:.2f}. Consecutive losses: {self.consecutive_losses}")
        self.monitoring_system.alert_manager.create_alert(
            "Loss Recorded", f"Trade resulted in loss: ${loss_usd:.2f}", "warning", "SafetyManager"
        )
        self._check_risk_limits()

    def _check_risk_limits(self):
        if self.risk_config["circuit_breaker_enabled"]:
            if self.daily_profit_loss < -self.risk_config["max_daily_loss_usd"]:
                self._activate_circuit_breaker("Max daily loss exceeded")
            elif self.consecutive_losses >= self.risk_config["max_consecutive_losses"]:
                self._activate_circuit_breaker("Max consecutive losses reached")

    def _activate_circuit_breaker(self, reason: str):
        if not self.circuit_breaker_active:
            self.circuit_breaker_active = True
            logger.critical(f"CIRCUIT BREAKER ACTIVATED: {reason}")
            self.monitoring_system.alert_manager.create_alert(
                "Circuit Breaker Activated", reason, "critical", "SafetyManager"
            )

    def deactivate_circuit_breaker(self):
        if self.circuit_breaker_active:
            self.circuit_breaker_active = False
            self.consecutive_losses = 0 # Reset consecutive losses on deactivation
            logger.info("Circuit breaker deactivated.")
            self.monitoring_system.alert_manager.create_alert(
                "Circuit Breaker Deactivated", "Manual deactivation", "info", "SafetyManager"
            )

    def is_circuit_breaker_active(self) -> bool:
        return self.circuit_breaker_active

    def get_safety_status(self) -> Dict[str, Any]:
        return {
            "daily_profit_loss": self.daily_profit_loss,
            "consecutive_losses": self.consecutive_losses,
            "circuit_breaker_active": self.circuit_breaker_active,
            "last_trade_time": self.last_trade_time,
            "max_daily_loss_usd": self.risk_config["max_daily_loss_usd"],
            "max_consecutive_losses": self.risk_config["max_consecutive_losses"]
        }
        
    def _initialize_safety_rules(self) -> Dict[SafetyRule, Dict[str, Any]]:
        """Initialize safety rules with thresholds and actions."""
        return {
            SafetyRule.DAILY_LOSS_LIMIT: {
                'threshold': RISK_CONFIG['max_daily_loss_usd'],
                'action': 'emergency_stop',
                'severity': SafetyLevel.RED
            },
            SafetyRule.SINGLE_TRADE_LOSS: {
                'threshold': RISK_CONFIG['max_single_trade_loss_usd'],
                'action': 'pause_trading',
                'severity': SafetyLevel.ORANGE
            },
            SafetyRule.CONSECUTIVE_LOSSES: {
                'threshold': 5,  # 5 consecutive losses
                'action': 'pause_trading',
                'severity': SafetyLevel.ORANGE
            },
            SafetyRule.BALANCE_THRESHOLD: {
                'threshold': 0.1,  # 10% of initial balance
                'action': 'restrict_trading',
                'severity': SafetyLevel.YELLOW
            },
            SafetyRule.PRICE_DEVIATION: {
                'threshold': 0.05,  # 5% price deviation
                'action': 'restrict_pair',
                'severity': SafetyLevel.YELLOW
            },
            SafetyRule.API_ERROR_RATE: {
                'threshold': 0.1,  # 10% error rate
                'action': 'restrict_exchange',
                'severity': SafetyLevel.ORANGE
            },
            SafetyRule.EXECUTION_TIME: {
                'threshold': 5000,  # 5 seconds
                'action': 'warning',
                'severity': SafetyLevel.YELLOW
            },
            SafetyRule.SPREAD_ANOMALY: {
                'threshold': 0.02,  # 2% spread
                'action': 'restrict_pair',
                'severity': SafetyLevel.YELLOW
            },
            SafetyRule.MARKET_VOLATILITY: {
                'threshold': 0.1,  # 10% volatility
                'action': 'pause_trading',
                'severity': SafetyLevel.ORANGE
            }
        }
    
    async def check_safety_before_trade(self, opportunity: ArbitrageOpportunity) -> Tuple[bool, Optional[str]]:
        """Check if it's safe to execute a trade."""
        
        # Check emergency stop
        if self.emergency_stop_active:
            return False, f"Emergency stop active: {self.emergency_stop_reason}"
        
        # Check if trading is paused
        if self.trading_paused:
            return False, "Trading is currently paused due to safety concerns"
        
        # Check restricted pairs
        if opportunity.symbol in self.restricted_pairs:
            return False, f"Trading pair {opportunity.symbol} is restricted"
        
        # Check restricted exchanges
        if (opportunity.buy_exchange in self.restricted_exchanges or 
            opportunity.sell_exchange in self.restricted_exchanges):
            return False, "One or both exchanges are restricted"
        
        # Check daily trade limit
        if self.metrics.total_trades_today >= TRADING_CONFIG['max_daily_trades']:
            return False, "Daily trade limit reached"
        
        # Check price deviation
        if self._check_price_deviation(opportunity):
            return False, "Price deviation exceeds safety threshold"
        
        # Check spread anomaly
        if self._check_spread_anomaly(opportunity):
            return False, "Spread anomaly detected"
        
        # Check minimum profit threshold with safety margin
        safety_margin = 1.5  # 50% safety margin
        min_profit = TRADING_CONFIG['min_profit_threshold'] * safety_margin
        if opportunity.potential_profit_pct < min_profit:
            return False, f"Profit below safety threshold ({min_profit:.4f}%)"
        
        return True, None
    
    def _check_price_deviation(self, opportunity: ArbitrageOpportunity) -> bool:
        """Check if price deviation is within safe limits."""
        # Calculate price deviation from average
        avg_price = (opportunity.buy_price + opportunity.sell_price) / 2
        deviation = abs(opportunity.sell_price - opportunity.buy_price) / avg_price
        
        threshold = self.safety_rules[SafetyRule.PRICE_DEVIATION]['threshold']
        
        if deviation > threshold:
            self._record_violation(
                SafetyRule.PRICE_DEVIATION,
                f"Price deviation {deviation:.4f} exceeds threshold {threshold:.4f}",
                deviation,
                threshold,
                "price_monitor",
                {'symbol': opportunity.symbol, 'buy_price': opportunity.buy_price, 'sell_price': opportunity.sell_price}
            )
            return True
        
        return False
    
    def _check_spread_anomaly(self, opportunity: ArbitrageOpportunity) -> bool:
        """Check for unusual spread that might indicate data issues."""
        # This is a simplified check - in practice, you'd compare against historical spreads
        spread_pct = opportunity.potential_profit_pct
        threshold = self.safety_rules[SafetyRule.SPREAD_ANOMALY]['threshold']
        
        if spread_pct > threshold:
            self._record_violation(
                SafetyRule.SPREAD_ANOMALY,
                f"Spread {spread_pct:.4f} exceeds normal threshold {threshold:.4f}",
                spread_pct,
                threshold,
                "price_monitor",
                {'symbol': opportunity.symbol, 'spread': spread_pct}
            )
            return True
        
        return False
    
    def record_trade_result(self, trade: ArbitrageTrade):
        """Record trade result for safety monitoring."""
        
        # Update metrics
        self.metrics.total_trades_today += 1
        self.metrics.daily_pnl += trade.actual_profit_usd
        
        # Track consecutive losses
        if trade.actual_profit_usd < 0:
            self.metrics.consecutive_losses += 1
            self.metrics.last_trade_loss = abs(trade.actual_profit_usd)
        else:
            self.metrics.consecutive_losses = 0
        
        # Update execution time
        if trade.execution_time_ms:
            self.metrics.avg_execution_time = (
                (self.metrics.avg_execution_time * (self.metrics.total_trades_today - 1) + 
                 trade.execution_time_ms) / self.metrics.total_trades_today
            )
        
        # Store trade history
        trade_record = {
            'timestamp': trade.timestamp,
            'symbol': trade.opportunity.symbol,
            'profit_usd': trade.actual_profit_usd,
            'status': trade.status.value,
            'execution_time_ms': trade.execution_time_ms
        }
        self.trade_history.append(trade_record)
        
        # Keep only recent history
        if len(self.trade_history) > 1000:
            self.trade_history = self.trade_history[-500:]
        
        # Check safety rules after trade
        asyncio.create_task(self._check_post_trade_safety(trade))
    
    async def _check_post_trade_safety(self, trade: ArbitrageTrade):
        """Check safety rules after a trade is completed."""
        
        # Check daily loss limit
        if abs(self.metrics.daily_pnl) >= self.safety_rules[SafetyRule.DAILY_LOSS_LIMIT]['threshold']:
            await self._trigger_emergency_stop(
                f"Daily loss limit exceeded: ${abs(self.metrics.daily_pnl):.2f}"
            )
            return
        
        # Check single trade loss
        if (trade.actual_profit_usd < 0 and 
            abs(trade.actual_profit_usd) >= self.safety_rules[SafetyRule.SINGLE_TRADE_LOSS]['threshold']):
            self._record_violation(
                SafetyRule.SINGLE_TRADE_LOSS,
                f"Single trade loss ${abs(trade.actual_profit_usd):.2f} exceeds threshold",
                abs(trade.actual_profit_usd),
                self.safety_rules[SafetyRule.SINGLE_TRADE_LOSS]['threshold'],
                "trading_engine",
                {'trade_id': trade.id}
            )
            await self._pause_trading("Large single trade loss detected")
        
        # Check consecutive losses
        if self.metrics.consecutive_losses >= self.safety_rules[SafetyRule.CONSECUTIVE_LOSSES]['threshold']:
            self._record_violation(
                SafetyRule.CONSECUTIVE_LOSSES,
                f"{self.metrics.consecutive_losses} consecutive losses detected",
                self.metrics.consecutive_losses,
                self.safety_rules[SafetyRule.CONSECUTIVE_LOSSES]['threshold'],
                "trading_engine",
                {}
            )
            await self._pause_trading("Too many consecutive losses")
        
        # Check execution time
        if (trade.execution_time_ms and 
            trade.execution_time_ms >= self.safety_rules[SafetyRule.EXECUTION_TIME]['threshold']):
            self._record_violation(
                SafetyRule.EXECUTION_TIME,
                f"Execution time {trade.execution_time_ms}ms exceeds threshold",
                trade.execution_time_ms,
                self.safety_rules[SafetyRule.EXECUTION_TIME]['threshold'],
                "trading_engine",
                {'trade_id': trade.id}
            )
    
    def record_api_error(self, exchange: str, error_type: str):
        """Record API error for safety monitoring."""
        error_record = {
            'timestamp': time.time(),
            'exchange': exchange,
            'error_type': error_type
        }
        self.error_history.append(error_record)
        
        # Keep only recent history (last hour)
        cutoff_time = time.time() - 3600
        self.error_history = [e for e in self.error_history if e['timestamp'] >= cutoff_time]
        
        # Calculate error rate for this exchange
        exchange_errors = [e for e in self.error_history if e['exchange'] == exchange]
        error_rate = len(exchange_errors) / max(len(self.error_history), 1)
        
        self.metrics.api_error_rate = error_rate
        
        # Check if error rate exceeds threshold
        threshold = self.safety_rules[SafetyRule.API_ERROR_RATE]['threshold']
        if error_rate >= threshold:
            self._record_violation(
                SafetyRule.API_ERROR_RATE,
                f"API error rate {error_rate:.2%} for {exchange} exceeds threshold {threshold:.2%}",
                error_rate,
                threshold,
                "exchange_manager",
                {'exchange': exchange, 'recent_errors': len(exchange_errors)}
            )
            self._restrict_exchange(exchange, f"High API error rate: {error_rate:.2%}")
    
    def _record_violation(self, rule: SafetyRule, message: str, current_value: float,
                         threshold_value: float, component: str, context: Dict[str, Any]):
        """Record a safety rule violation."""
        
        rule_config = self.safety_rules[rule]
        violation = SafetyViolation(
            rule=rule,
            severity=rule_config['severity'],
            message=message,
            current_value=current_value,
            threshold_value=threshold_value,
            timestamp=time.time(),
            component=component,
            context=context
        )
        
        self.violations.append(violation)
        
        # Update safety level
        if violation.severity.value > self.safety_level.value:
            self.safety_level = violation.severity
        
        # Log violation
        logger.warning(f"Safety violation [{rule.value}]: {message}")
        
        # Report to error handler
        self.error_handler.handle_error(
            category=ErrorCategory.TRADING,
            severity=ErrorSeverity.HIGH if violation.severity == SafetyLevel.RED else ErrorSeverity.MEDIUM,
            component=component,
            message=f"Safety violation: {message}",
            context=context
        )
        
        # Execute action
        action = rule_config['action']
        if action == 'emergency_stop':
            asyncio.create_task(self._trigger_emergency_stop(message))
        elif action == 'pause_trading':
            asyncio.create_task(self._pause_trading(message))
        elif action == 'restrict_pair' and 'symbol' in context:
            self._restrict_pair(context['symbol'], message)
        elif action == 'restrict_exchange' and 'exchange' in context:
            self._restrict_exchange(context['exchange'], message)
    
    async def _trigger_emergency_stop(self, reason: str):
        """Trigger emergency stop of all trading."""
        self.emergency_stop_active = True
        self.emergency_stop_reason = reason
        self.safety_level = SafetyLevel.RED
        self.metrics.emergency_stops_triggered += 1
        
        logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")
        
        # This would signal the trading engine to stop immediately
        # In practice, this would call the trading engine's emergency stop method
    
    async def _pause_trading(self, reason: str):
        """Pause all trading temporarily."""
        self.trading_paused = True
        self.safety_level = SafetyLevel.ORANGE
        
        logger.warning(f"TRADING PAUSED: {reason}")
        
        # Auto-resume after a cooldown period (e.g., 5 minutes)
        await asyncio.sleep(300)  # 5 minutes
        
        if self.trading_paused:  # Check if still paused (not manually resumed)
            await self.resume_trading("Auto-resume after cooldown period")
    
    async def resume_trading(self, reason: str = "Manual resume"):
        """Resume trading after pause."""
        self.trading_paused = False
        
        # Reset safety level if no critical violations
        if not any(v.severity == SafetyLevel.RED for v in self.violations[-10:]):
            self.safety_level = SafetyLevel.GREEN
        
        logger.info(f"TRADING RESUMED: {reason}")
    
    def _restrict_pair(self, symbol: str, reason: str):
        """Restrict trading for a specific pair."""
        if symbol not in self.restricted_pairs:
            self.restricted_pairs.append(symbol)
            logger.warning(f"PAIR RESTRICTED: {symbol} - {reason}")
    
    def _restrict_exchange(self, exchange: str, reason: str):
        """Restrict trading on a specific exchange."""
        if exchange not in self.restricted_exchanges:
            self.restricted_exchanges.append(exchange)
            logger.warning(f"EXCHANGE RESTRICTED: {exchange} - {reason}")
    
    def clear_restriction(self, restriction_type: str, identifier: str):
        """Clear a specific restriction."""
        if restriction_type == 'pair' and identifier in self.restricted_pairs:
            self.restricted_pairs.remove(identifier)
            logger.info(f"Pair restriction cleared: {identifier}")
        elif restriction_type == 'exchange' and identifier in self.restricted_exchanges:
            self.restricted_exchanges.remove(identifier)
            logger.info(f"Exchange restriction cleared: {identifier}")
    
    def reset_emergency_stop(self, reason: str = "Manual reset"):
        """Reset emergency stop (requires manual intervention)."""
        if self.emergency_stop_active:
            self.emergency_stop_active = False
            self.emergency_stop_reason = None
            self.safety_level = SafetyLevel.YELLOW  # Start with caution
            
            logger.info(f"EMERGENCY STOP RESET: {reason}")
    
    def get_safety_status(self) -> Dict[str, Any]:
        """Get current safety status."""
        recent_violations = [v for v in self.violations if time.time() - v.timestamp < 3600]
        
        return {
            'safety_level': self.safety_level.name,
            'emergency_stop_active': self.emergency_stop_active,
            'emergency_stop_reason': self.emergency_stop_reason,
            'trading_paused': self.trading_paused,
            'restricted_pairs': self.restricted_pairs,
            'restricted_exchanges': self.restricted_exchanges,
            'metrics': {
                'daily_pnl': self.metrics.daily_pnl,
                'consecutive_losses': self.metrics.consecutive_losses,
                'total_trades_today': self.metrics.total_trades_today,
                'api_error_rate': self.metrics.api_error_rate,
                'avg_execution_time': self.metrics.avg_execution_time,
                'emergency_stops_triggered': self.metrics.emergency_stops_triggered
            },
            'recent_violations': len(recent_violations),
            'violation_summary': {
                rule.value: len([v for v in recent_violations if v.rule == rule])
                for rule in SafetyRule
            }
        }
    
    def reset_daily_metrics(self):
        """Reset daily metrics (called at start of new trading day)."""
        self.metrics.daily_pnl = 0.0
        self.metrics.consecutive_losses = 0
        self.metrics.total_trades_today = 0
        self.metrics.emergency_stops_triggered = 0
        
        # Clear old violations (keep only last 24 hours)
        cutoff_time = time.time() - 86400
        self.violations = [v for v in self.violations if v.timestamp >= cutoff_time]
        
        # Reset safety level if no recent critical violations
        if not any(v.severity == SafetyLevel.RED for v in self.violations):
            self.safety_level = SafetyLevel.GREEN
        
        logger.info("Daily safety metrics reset")
    
    async def perform_safety_check(self):
        """Perform comprehensive safety check."""
        current_time = time.time()
        
        # Skip if checked recently
        if current_time - self.last_safety_check < self.safety_check_interval:
            return
        
        self.last_safety_check = current_time
        
        # Check for stale data
        if current_time - self.metrics.last_balance_check > 300:  # 5 minutes
            logger.warning("Balance data is stale - safety check may be incomplete")
        
        # Check system resources
        try:
            import psutil
            
            # Memory check
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                self._record_violation(
                    SafetyRule.BALANCE_THRESHOLD,  # Reusing for system resources
                    f"High memory usage: {memory.percent:.1f}%",
                    memory.percent,
                    90,
                    "system",
                    {'resource': 'memory'}
                )
            
            # CPU check
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 95:
                self._record_violation(
                    SafetyRule.BALANCE_THRESHOLD,  # Reusing for system resources
                    f"High CPU usage: {cpu_percent:.1f}%",
                    cpu_percent,
                    95,
                    "system",
                    {'resource': 'cpu'}
                )
        
        except ImportError:
            pass  # psutil not available
        
        logger.debug("Safety check completed")

