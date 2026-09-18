import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = os.environ["TELEGRAM_TOKEN"]

PORT = int(os.environ.get("PORT", "10000"))
PUBLIC_URL = os.environ["RENDER_EXTERNAL_URL"]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для изучения казахского языка."
    )


def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{PUBLIC_URL}/telegram",
        url_path="telegram",
    )


if __name__ == "__main__":
    main()
