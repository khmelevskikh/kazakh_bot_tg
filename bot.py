import os

from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)


TOKEN = os.environ["TELEGRAM_TOKEN"]

app = Flask(__name__)

telegram_app = Application.builder().token(TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для изучения казахского языка."
    )


telegram_app.add_handler(
    CommandHandler("start", start)
)


@app.route("/")
def index():
    return "Kazakh bot is running"


@app.route("/webhook", methods=["POST"])
async def webhook():
    update = Update.de_json(
        request.get_json(force=True),
        telegram_app.bot
    )

    await telegram_app.process_update(update)

    return "OK"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
