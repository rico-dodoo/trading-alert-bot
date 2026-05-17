import json
import os
import sys
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]
from dotenv import load_dotenv  # type: ignore[import-untyped]
from telegram import Update  # type: ignore[import-untyped]
from telegram.error import TimedOut  # type: ignore[import-untyped]
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes  # type: ignore[import-untyped]
from telegram.request import HTTPXRequest  # type: ignore[import-untyped]


# ---------- PROJECT SETTINGS ----------

PROJECT_FOLDER = Path(__file__).resolve().parent
ENV_FILE_PATH = PROJECT_FOLDER / ".env"
ALERTS_FILE = PROJECT_FOLDER / "alerts.json"
GOLD_API_BASE_URL = "https://api.gold-api.com/price"


# ---------- ENVIRONMENT SETUP ----------

def load_environment() -> tuple[str, int]:
    """Load the Telegram token and check interval from the .env file."""
    print("Starting main.py...", flush=True)
    print(f"Project folder: {PROJECT_FOLDER}", flush=True)
    print(f"Looking for .env file here: {ENV_FILE_PATH}", flush=True)

    if not ENV_FILE_PATH.exists():
        raise FileNotFoundError(
            "Your .env file is missing.\n\n"
            f"Create this file: {ENV_FILE_PATH}\n\n"
            "Inside the .env file, add:\n"
            "TELEGRAM_BOT_TOKEN=your_new_botfather_token_here\n"
            "CHECK_INTERVAL_SECONDS=60"
        )

    load_dotenv(dotenv_path=ENV_FILE_PATH)

    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    check_interval_text = os.getenv("CHECK_INTERVAL_SECONDS", "60")

    if not telegram_bot_token:
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is missing inside your .env file.\n\n"
            "Open your .env file and add this line:\n"
            "TELEGRAM_BOT_TOKEN=your_new_botfather_token_here"
        )

    if telegram_bot_token == "your_new_botfather_token_here":
        raise ValueError(
            "You still have the example token text in your .env file.\n\n"
            "Replace it with your real new token from BotFather."
        )

    try:
        check_interval_seconds = int(check_interval_text)
    except ValueError as error:
        raise ValueError(
            "CHECK_INTERVAL_SECONDS must be a number. Example:\n"
            "CHECK_INTERVAL_SECONDS=60"
        ) from error

    if check_interval_seconds < 10:
        raise ValueError("CHECK_INTERVAL_SECONDS should be at least 10 seconds.")

    print("Telegram token found.", flush=True)
    return telegram_bot_token, check_interval_seconds


# ---------- FILE FUNCTIONS ----------

def load_alerts() -> list[dict[str, Any]]:
    """Load saved alerts from alerts.json."""
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as file:
            alerts = json.load(file)

        if isinstance(alerts, list):
            return alerts

        return []

    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []


def save_alerts(alerts: list[dict[str, Any]]) -> None:
    """Save alerts to alerts.json."""
    with open(ALERTS_FILE, "w", encoding="utf-8") as file:
        json.dump(alerts, file, indent=4)


# ---------- PRICE FUNCTIONS ----------

def fetch_price_from_gold_api(symbol: str) -> float:
    """Fetch a price from Gold-API.com."""
    url = f"{GOLD_API_BASE_URL}/{symbol}"

    response = requests.get(url, timeout=15)
    response.raise_for_status()

    data = response.json()

    if "price" not in data:
        raise ValueError(f"Price was not found in API response: {data}")

    return float(data["price"])


def get_btc_price() -> float:
    """Get the current Bitcoin price in USD."""
    return fetch_price_from_gold_api("BTC")


def get_gold_price() -> float:
    """Get the current Gold price in USD."""
    return fetch_price_from_gold_api("XAU")


def get_price(asset: str) -> float:
    """Get the price depending on the asset name."""
    asset = asset.lower()

    if asset == "btc":
        return get_btc_price()

    if asset == "gold":
        return get_gold_price()

    raise ValueError("Unknown asset. Use btc or gold.")


# ---------- TELEGRAM HELPER FUNCTIONS ----------

def get_message(update: Update) -> Any:
    """Safely get the Telegram message from an update."""
    if update.message is None:
        raise ValueError("This command can only be used in a normal chat message.")

    return update.message


def get_chat_id(update: Update) -> int:
    """Safely get the Telegram chat ID from an update."""
    if update.effective_chat is None:
        raise ValueError("Could not find the Telegram chat for this update.")

    return update.effective_chat.id


# ---------- TELEGRAM COMMANDS ----------

async def start(update: Update, context: Any) -> None:
    """Send a welcome message and show all available commands."""
    telegram_message = get_message(update)

    message = """
Hello! I am your BTC and Gold alert bot.

Commands:

/price
Shows current BTC and Gold prices.

/alert btc above 100000
Alerts you when Bitcoin goes above 100000 USD.

/alert btc below 90000
Alerts you when Bitcoin goes below 90000 USD.

/alert gold above 2500
Alerts you when Gold goes above 2500 USD.

/alert gold below 2300
Alerts you when Gold goes below 2300 USD.

/alerts
Shows your active alerts.

/delete 1
Deletes alert number 1.
"""
    await telegram_message.reply_text(message)


async def price(update: Update, context: Any) -> None:
    """Show the current BTC and Gold prices."""
    telegram_message = get_message(update)

    try:
        btc_price = get_btc_price()
        gold_price = get_gold_price()

        message = (
            "Current prices:\n\n"
            f"Bitcoin BTC/USD: ${btc_price:,.2f}\n"
            f"Gold XAU/USD: ${gold_price:,.2f}"
        )

        await telegram_message.reply_text(message)

    except requests.RequestException as error:
        await telegram_message.reply_text(
            "Sorry, I could not connect to the price API right now.\n\n"
            f"Error: {error}"
        )
    except Exception as error:
        await telegram_message.reply_text(
            "Sorry, I could not fetch prices right now.\n\n"
            f"Error: {error}"
        )


async def alert(update: Update, context: Any) -> None:
    """Create a price alert."""
    telegram_message = get_message(update)

    try:
        args = context.args or []

        if len(args) != 3:
            await telegram_message.reply_text(
                "Wrong format.\n\n"
                "Use:\n"
                "/alert btc above 100000\n"
                "/alert gold below 2300"
            )
            return

        asset = args[0].lower()
        direction = args[1].lower()
        target_price = float(args[2])
        chat_id = get_chat_id(update)

        if asset not in ["btc", "gold"]:
            await telegram_message.reply_text("Asset must be btc or gold.")
            return

        if direction not in ["above", "below"]:
            await telegram_message.reply_text("Direction must be above or below.")
            return

        if target_price <= 0:
            await telegram_message.reply_text("The target price must be greater than 0.")
            return

        alerts = load_alerts()

        new_alert = {
            "chat_id": chat_id,
            "asset": asset,
            "direction": direction,
            "target_price": target_price,
        }

        alerts.append(new_alert)
        save_alerts(alerts)

        await telegram_message.reply_text(
            "Alert created:\n\n"
            f"{asset.upper()} {direction} ${target_price:,.2f}"
        )

    except ValueError:
        await telegram_message.reply_text("The target price must be a valid number.")
    except Exception as error:
        await telegram_message.reply_text(f"Error creating alert: {error}")


async def alerts_command(update: Update, context: Any) -> None:
    """Show all active alerts for the current Telegram chat."""
    telegram_message = get_message(update)
    chat_id = get_chat_id(update)
    alerts = load_alerts()

    user_alerts = [
        alert_item for alert_item in alerts
        if alert_item.get("chat_id") == chat_id
    ]

    if not user_alerts:
        await telegram_message.reply_text("You have no active alerts.")
        return

    message = "Your active alerts:\n\n"

    for index, alert_item in enumerate(user_alerts, start=1):
        message += (
            f"{index}. {alert_item['asset'].upper()} "
            f"{alert_item['direction']} "
            f"${float(alert_item['target_price']):,.2f}\n"
        )

    await telegram_message.reply_text(message)


async def delete_alert(update: Update, context: Any) -> None:
    """Delete an active alert."""
    telegram_message = get_message(update)

    try:
        args = context.args or []

        if len(args) != 1:
            await telegram_message.reply_text("Use: /delete 1")
            return

        alert_number = int(args[0])
        chat_id = get_chat_id(update)
        alerts = load_alerts()

        user_alerts = [
            alert_item for alert_item in alerts
            if alert_item.get("chat_id") == chat_id
        ]

        if alert_number < 1 or alert_number > len(user_alerts):
            await telegram_message.reply_text("That alert number does not exist.")
            return

        alert_to_delete = user_alerts[alert_number - 1]
        alerts.remove(alert_to_delete)
        save_alerts(alerts)

        await telegram_message.reply_text("Alert deleted successfully.")

    except ValueError:
        await telegram_message.reply_text("Please enter a valid alert number.")
    except Exception as error:
        await telegram_message.reply_text(f"Error deleting alert: {error}")


# ---------- AUTOMATIC ALERT CHECKER ----------

async def check_alerts(context: Any) -> None:
    """Check whether any saved alert has been triggered."""
    alerts = load_alerts()

    if not alerts:
        return

    remaining_alerts = []

    for alert_item in alerts:
        try:
            asset = str(alert_item["asset"])
            direction = str(alert_item["direction"])
            target_price = float(alert_item["target_price"])
            chat_id = int(alert_item["chat_id"])

            current_price = get_price(asset)

            triggered = (
                direction == "above" and current_price >= target_price
            ) or (
                direction == "below" and current_price <= target_price
            )

            if triggered:
                message = (
                    "PRICE ALERT TRIGGERED\n\n"
                    f"{asset.upper()} is now ${current_price:,.2f}\n"
                    f"Your alert was: {direction} ${target_price:,.2f}"
                )

                await context.bot.send_message(chat_id=chat_id, text=message)
                continue

            remaining_alerts.append(alert_item)

        except Exception as error:
            print(f"Error checking alert: {error}", flush=True)
            remaining_alerts.append(alert_item)

    save_alerts(remaining_alerts)


# ---------- MAIN BOT SETUP ----------

def main() -> None:
    """Start the Telegram bot."""
    try:
        telegram_bot_token, check_interval_seconds = load_environment()

        telegram_request = HTTPXRequest(
            connect_timeout=30,
            read_timeout=60,
            write_timeout=30,
            pool_timeout=30,
        )

        app = (
            ApplicationBuilder()
            .token(telegram_bot_token)
            .request(telegram_request)
            .build()
        )

        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("price", price))
        app.add_handler(CommandHandler("alert", alert))
        app.add_handler(CommandHandler("alerts", alerts_command))
        app.add_handler(CommandHandler("delete", delete_alert))

        if app.job_queue is None:
            raise ValueError(
                "JobQueue is not installed.\n\n"
                "Run this command in your terminal:\n"
                "pip install 'python-telegram-bot[job-queue]'"
            )

        app.job_queue.run_repeating(
            check_alerts,
            interval=check_interval_seconds,
            first=10,
        )

        print("Connecting to Telegram...", flush=True)
        app.run_polling(
            bootstrap_retries=5,
            drop_pending_updates=True,
        )

    except TimedOut:
        print("\nERROR: Telegram did not respond in time.\n", flush=True)
        print(
            "This usually means your internet connection, VPN, firewall, or network is blocking or slowing Telegram.\n"
            "Try switching Wi-Fi, turning VPN off/on, or using your phone hotspot, then run: python3 -u main.py",
            flush=True,
        )
        sys.exit(1)

    except Exception as error:
        print("\nERROR: The bot could not start.\n", flush=True)
        print(error, flush=True)
        print("\nCheck the message above and fix that issue first.\n", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()