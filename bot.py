import os
import random
import re

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


TOKEN = os.environ["TELEGRAM_TOKEN"]

PORT = int(os.environ.get("PORT", "10000"))
PUBLIC_URL = os.environ["RENDER_EXTERNAL_URL"]


def load_words(filename):
    """Read words from Markdown table."""

    words = []

    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            # Skip Markdown separator
            if re.match(r"^\|\s*-+", line):
                continue

            match = re.match(
                r"^\|\s*(.*?)\s*\|\s*(.*?)\s*\|$",
                line
            )

            if not match:
                continue

            kazakh = match.group(1).strip()
            russian = match.group(2).strip()

            # Skip header
            if kazakh.lower() in (
                "казахское",
                "казахское (исправлено)"
            ):
                continue

            if kazakh and russian:
                words.append({
                    "kazakh": kazakh,
                    "russian": russian,
                })

    return words


# Load dictionary when the bot starts
WORDS = load_words("words.md")

print(f"Loaded {len(WORDS)} words")


# Statistics for users.
#
# Example:
# {
#     123456789: {
#         "total": 10,
#         "correct": 8,
#         "wrong": 2
#     }
# }
#
# The data exists only while the bot is running.
statistics = {}


def get_statistics(user_id):
    if user_id not in statistics:
        statistics[user_id] = {
            "total": 0,
            "correct": 0,
            "wrong": 0,
        }

    return statistics[user_id]


def get_question():
    """Generate random question."""

    question = random.choice(WORDS)

    correct_answer = question["russian"]

    # Get words with different translations
    other_words = [
        word for word in WORDS
        if word["russian"] != correct_answer
    ]

    # Three wrong answers
    wrong_answers = random.sample(
        other_words,
        min(3, len(other_words))
    )

    answers = [
        correct_answer,
        *[word["russian"] for word in wrong_answers]
    ]

    random.shuffle(answers)

    return question, answers


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для изучения казахского языка.\n\n"
        "Команды:\n"
        "/quiz — начать тест\n"
        "/stats — показать статистику"
    )


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start quiz."""

    await send_question(
        update.effective_chat.id,
        context
    )


async def send_question(chat_id, context):
    """Send a new question."""

    question, answers = get_question()

    # Store correct answer for this chat
    context.user_data["current_question"] = {
        "kazakh": question["kazakh"],
        "correct": question["russian"],
    }

    buttons = []

    for answer in answers:
        buttons.append([
            InlineKeyboardButton(
                answer,
                callback_data=f"answer:{answer}"
            )
        ])

    keyboard = InlineKeyboardMarkup(buttons)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🇰🇿 <b>{question['kazakh']}</b>\n\n"
             f"Выберите перевод:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process user's answer."""

    query = update.callback_query
    await query.answer()

    question = context.user_data.get("current_question")

    if not question:
        await query.edit_message_text(
            "Вопрос устарел. Нажмите /quiz, чтобы начать новый тест."
        )
        return

    selected_answer = query.data[len("answer:"):]
    correct_answer = question["correct"]

    stats = get_statistics(update.effective_user.id)

    stats["total"] += 1

    if selected_answer == correct_answer:
        stats["correct"] += 1

        result = (
            "✅ <b>Правильно!</b>"
        )
    else:
        stats["wrong"] += 1

        result = (
            "❌ <b>Неправильно.</b>\n\n"
            f"Правильный ответ: <b>{correct_answer}</b>"
        )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➡️ Следующее слово",
                callback_data="next"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Статистика",
                callback_data="stats"
            )
        ],
    ])

    await query.edit_message_text(
        f"🇰🇿 <b>{question['kazakh']}</b>\n\n"
        f"{result}",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show next question."""

    query = update.callback_query
    await query.answer()

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show statistics."""

    user_id = update.effective_user.id
    user_stats = get_statistics(user_id)

    total = user_stats["total"]
    correct = user_stats["correct"]
    wrong = user_stats["wrong"]

    if total:
        percentage = correct / total * 100
    else:
        percentage = 0

    text = (
        "📊 <b>Твоя статистика</b>\n\n"
        f"Всего вопросов: <b>{total}</b>\n"
        f"Правильных: <b>{correct}</b>\n"
        f"Неправильных: <b>{wrong}</b>\n"
        f"Результат: <b>{percentage:.1f}%</b>"
    )

    if update.callback_query:
        query = update.callback_query
        await query.answer()

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "➡️ Следующее слово",
                    callback_data="next"
                )
            ]
        ])

        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode="HTML",
        )


async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    """Handle all inline buttons."""

    query = update.callback_query

    if query.data.startswith("answer:"):
        await answer(update, context)

    elif query.data == "next":
        await next_question(update, context)

    elif query.data == "stats":
        await stats(update, context)


def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("quiz", quiz)
    )

    application.add_handler(
        CommandHandler("stats", stats)
    )

    application.add_handler(
        CallbackQueryHandler(button_handler)
    )

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{PUBLIC_URL}/telegram",
        url_path="telegram",
    )


if __name__ == "__main__":
    main()
