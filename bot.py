from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


TOKEN = "СЮДА_ВСТАВЬ_ТОКЕН"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для изучения казахского языка."
    )


def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    print("Bot started...")
    application.run_polling()


if __name__ == "__main__":
    main()
