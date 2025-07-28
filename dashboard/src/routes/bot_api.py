"""
API routes for the arbitrage bot dashboard.
"""

from flask import Blueprint, jsonify, request
import asyncio
import threading
import time
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

bot_api = Blueprint("bot_api", __name__)

# These will be set by the main application (dashboard/src/main.py)
_bot_instance = None
_monitoring_system = None
_bot_thread: Optional[threading.Thread] = None

def set_bot_instances(bot_instance, monitoring_system):
    """Sets the global bot and monitoring instances for the blueprint."""
    global _bot_instance, _monitoring_system
    _bot_instance = bot_instance
    _monitoring_system = monitoring_system
    logger.info("Bot and monitoring instances set in bot_api blueprint.")

async def _run_bot_async():
    """Internal async function to run the bot's main loop."""
    global _bot_instance, _monitoring_system
    
    if _bot_instance is None or _monitoring_system is None:
        logger.error("Bot or monitoring system instance is None. Cannot start.")
        return

    try:
        logger.info("Attempting to initialize and start bot components...")
        await _bot_instance.initialize()
        await _monitoring_system.start()
        await _bot_instance.start()
        logger.info("Bot and monitoring system started successfully.")
    except Exception as e:
        logger.error(f"Error during bot startup: {e}", exc_info=True)
        # Attempt to stop if partial startup occurred
        if _bot_instance and _bot_instance.is_running:
            await _bot_instance.stop()
        if _monitoring_system and _monitoring_system.is_running:
            await _monitoring_system.stop()

def _run_bot_in_thread_target():
    """Target function for the bot thread to run the async bot."""
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_run_bot_async())
    loop.close()
    logger.info("Bot thread finished execution.")

@bot_api.route("/status", methods=["GET"])
def get_bot_status():
    """Get current bot status."""
    try:
        if _bot_instance is None:
            logger.warning("Status requested but _bot_instance is None.")
            return jsonify({
                "status": "stopped",
                "message": "Bot instance not initialized"
            }), 200
        
        status_data = _bot_instance.get_status()
        
        # Also include monitoring system status
        monitoring_status = "running" if _monitoring_system and _monitoring_system.is_running else "stopped"
        status_data["monitoring_system_status"] = monitoring_status

        return jsonify({
            "status": "success",
            "data": status_data
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting bot status: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/start", methods=["POST"])
def start_bot():
    """Start the arbitrage bot."""
    global _bot_thread
    
    if _bot_instance is None or _monitoring_system is None:
        return jsonify({
            "status": "error",
            "message": "Bot or monitoring system not initialized. Check server logs."
        }), 500

    if _bot_instance.is_running:
        return jsonify({
            "status": "error",
            "message": "Bot is already running"
        }), 400
    
    try:
        logger.info("Received request to start bot.")
        _bot_thread = threading.Thread(target=_run_bot_in_thread_target, daemon=True)
        _bot_thread.start()
        
        # Give it a moment to start and update its internal state
        time.sleep(2) 
        
        return jsonify({
            "status": "success",
            "message": "Bot start initiated. Check status for updates."
        }), 200
        
    except Exception as e:
        logger.error(f"Error initiating bot start: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Failed to initiate bot start: {str(e)}"
        }), 500

@bot_api.route("/stop", methods=["POST"])
def stop_bot():
    """Stop the arbitrage bot."""
    if _bot_instance is None or _monitoring_system is None:
        return jsonify({
            "status": "error",
            "message": "Bot or monitoring system not initialized."
        }), 500

    if not _bot_instance.is_running:
        return jsonify({
            "status": "error",
            "message": "Bot is not running"
        }), 400
    
    try:
        logger.info("Received request to stop bot. Signaling shutdown event.")
        # Signal the bot to stop (this will be picked up by the bot's main loop)
        _bot_instance.shutdown_event.set()
        
        # Optionally, wait for the thread to finish, but don't block indefinitely
        # if _bot_thread and _bot_thread.is_alive():
        #     _bot_thread.join(timeout=5) # Wait up to 5 seconds

        return jsonify({
            "status": "success",
            "message": "Bot stop signal sent. Bot should shut down shortly."
        }), 200
        
    except Exception as e:
        logger.error(f"Error sending stop signal to bot: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": f"Failed to send stop signal: {str(e)}"
        }), 500

@bot_api.route("/trading/enable", methods=["POST"])
def enable_trading():
    """Enable trading."""
    try:
        if _bot_instance is None:
            return jsonify({
                "status": "error",
                "message": "Bot is not running"
            }), 400
        
        success = _bot_instance.trading_engine.enable_trading()
        
        if success:
            return jsonify({
                "status": "success",
                "message": "Trading enabled"
            }), 200
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to enable trading (circuit breaker may be triggered)"
            }), 400
        
    except Exception as e:
        logger.error(f"Error enabling trading: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/trading/disable", methods=["POST"])
def disable_trading():
    """Disable trading."""
    try:
        if _bot_instance is None:
            return jsonify({
                "status": "error",
                "message": "Bot is not running"
            }), 400
        
        _bot_instance.trading_engine.disable_trading()
        
        return jsonify({
            "status": "success",
            "message": "Trading disabled"
        }), 200
        
    except Exception as e:
        logger.error(f"Error disabling trading: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/trading/stats", methods=["GET"])
def get_trading_stats():
    """Get trading statistics."""
    try:
        if _bot_instance is None:
            return jsonify({
                "status": "error",
                "message": "Bot is not running"
            }), 400
        
        stats = _bot_instance.trading_engine.get_trading_statistics()
        
        return jsonify({
            "status": "success",
            "data": stats
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting trading stats: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/monitoring/alerts", methods=["GET"])
def get_alerts():
    """Get recent alerts."""
    try:
        if _monitoring_system is None:
            return jsonify({
                "status": "error",
                "message": "Monitoring system is not running"
            }), 400
        
        hours = request.args.get("hours", 24, type=int)
        alerts = _monitoring_system.alert_manager.get_recent_alerts(hours)
        
        # Convert alerts to dict format
        alert_data = []
        for alert in alerts:
            alert_data.append({
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type,
                "component": alert.component,
                "message": alert.message,
                "severity": alert.severity,
                "timestamp": alert.timestamp,
                "resolved": alert.resolved
            })
        
        return jsonify({
            "status": "success",
            "data": alert_data
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting alerts: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/monitoring/performance", methods=["GET"])
def get_performance_metrics():
    """Get performance metrics."""
    try:
        if _monitoring_system is None:
            return jsonify({
                "status": "error",
                "message": "Monitoring system is not running"
            }), 400
        
        metrics = _monitoring_system.performance_monitor.get_current_metrics()
        
        return jsonify({
            "status": "success",
            "data": metrics
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/monitoring/health", methods=["GET"])
def get_health_status():
    """Get health check status."""
    try:
        if _monitoring_system is None:
            return jsonify({
                "status": "error",
                "message": "Monitoring system is not running"
            }), 400
        
        # Run health check asynchronously
        # Create a new event loop for this thread if one doesn't exist
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        health_status = loop.run_until_complete(_monitoring_system.perform_health_check())
        
        return jsonify({
            "status": "success",
            "data": health_status
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting health status: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/exchanges/balances", methods=["GET"])
def get_exchange_balances():
    """Get balances across all exchanges."""
    try:
        if _bot_instance is None:
            return jsonify({
                "status": "error",
                "message": "Bot is not running"
            }), 400
        
        # This needs to be awaited as get_all_balances is async
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        balances = loop.run_until_complete(_bot_instance.exchange_manager.get_all_balances())
        
        return jsonify({
            "status": "success",
            "data": balances
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting exchange balances: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/market/summary", methods=["GET"])
def get_market_summary():
    """Get market summary."""
    try:
        if _bot_instance is None:
            return jsonify({
                "status": "error",
                "message": "Bot is not running"
            }), 400
        
        # This needs to be awaited as get_market_summary is async
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        summary = loop.run_until_complete(_bot_instance.price_monitor.get_market_summary())
        
        return jsonify({
            "status": "success",
            "data": summary
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting market summary: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/trades/active", methods=["GET"])
def get_active_trades():
    """Get active trades."""
    try:
        if _bot_instance is None:
            return jsonify({
                "status": "error",
                "message": "Bot is not running"
            }), 400
        
        active_trades = []
        for trade_id, trade in _bot_instance.trading_engine.active_trades.items():
            active_trades.append({
                "trade_id": trade.id,
                "symbol": trade.opportunity.symbol,
                "buy_exchange": trade.opportunity.buy_exchange,
                "sell_exchange": trade.opportunity.sell_exchange,
                "status": trade.status.value,
                "timestamp": trade.timestamp
            })
        
        return jsonify({
            "status": "success",
            "data": active_trades
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting active trades: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/trades/recent", methods=["GET"])
def get_recent_trades():
    """Get recent completed trades."""
    try:
        if _bot_instance is None:
            return jsonify({
                "status": "error",
                "message": "Bot is not running"
            }), 400
        
        limit = request.args.get("limit", 50, type=int)
        recent_trades = _bot_instance.trading_engine.completed_trades[-limit:]
        
        trade_data = []
        for trade in recent_trades:
            trade_data.append({
                "trade_id": trade.id,
                "symbol": trade.opportunity.symbol,
                "buy_exchange": trade.opportunity.buy_exchange,
                "sell_exchange": trade.opportunity.sell_exchange,
                "status": trade.status.value,
                "actual_profit_usd": trade.actual_profit_usd,
                "execution_time_ms": trade.execution_time_ms,
                "timestamp": trade.timestamp
            })
        
        return jsonify({
            "status": "success",
            "data": trade_data
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting recent trades: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bot_api.route("/config", methods=["GET"])
def get_config():
    """Get bot configuration."""
    try:
        # Import load_config here to avoid circular dependency at module level
        from config import load_config
        config_data = load_config()
        
        # Filter sensitive information before sending to frontend
        filtered_exchanges = {k: {key: val for key, val in v.items() if key not in ["api_key", "secret", "passphrase"]} for k, v in config_data["EXCHANGES"].items()}
        
        return jsonify({
            "status": "success",
            "data": {
                "TRADING_CONFIG": config_data["TRADING_CONFIG"],
                "RISK_CONFIG": config_data["RISK_CONFIG"],
                "PERFORMANCE_CONFIG": config_data["PERFORMANCE_CONFIG"],
                "MONITORING_CONFIG": {k: v for k, v in config_data["MONITORING_CONFIG"].items() if k not in ["telegram_bot_token", "email_password"]},
                "EXCHANGES": filtered_exchanges
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting config: {e}", exc_info=True)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
