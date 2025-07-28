"""
Main entry point for the Flask dashboard application.
"""

from flask import Flask, render_template
from flask_cors import CORS
import os
import sys
import logging

# Add the parent directory to the Python path to import bot modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Import ArbitrageBot and MonitoringSystem from their respective modules
from arbitrage_bot import ArbitrageBot
from monitoring import MonitoringSystem
from config import load_config

# Import the bot_api blueprint and its setter function
from routes.bot_api import bot_api, set_bot_instances

# Configure logging for the dashboard
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder="static", template_folder="static")
CORS(app)  # Enable CORS for all routes

# Load bot configuration
config = load_config()

# Initialize bot and monitoring system instances globally for the Flask app
# These instances will be passed to the bot_api blueprint
# They are initialized once when the Flask app starts
try:
    arbitrage_bot_instance = ArbitrageBot(config)
    monitoring_system_instance = MonitoringSystem(config)
    
    # Pass the initialized instances to the bot_api blueprint
    set_bot_instances(arbitrage_bot_instance, monitoring_system_instance)
    logger.info("ArbitrageBot and MonitoringSystem instances initialized and passed to bot_api.")
except Exception as e:
    logger.error(f"Failed to initialize bot or monitoring system: {e}")
    # If initialization fails, set instances to None to prevent further errors
    arbitrage_bot_instance = None
    monitoring_system_instance = None

# Register blueprints
app.register_blueprint(bot_api, url_prefix="/api/bot")

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    # Ensure the bot's main.py is not run directly here
    # The bot will be started/stopped via API calls to the dashboard
    app.run(host="0.0.0.0", port=5000, debug=True)
