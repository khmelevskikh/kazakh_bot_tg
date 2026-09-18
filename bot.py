import os
import random
import re
import math

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


# ---------------------------------------------------------
# Загрузка слов
# ---------------------------------------------------------

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


WORDS = load_words("words.md")

print(f"Loaded {len(WORDS)} words")


# ---------------------------------------------------------
# Статистика
# ---------------------------------------------------------

statistics = {}


def get_statistics(user_id):
    if user_id not in statistics:
        statistics[user_id] = {
            "total": 0,
            "correct": 0,
            "wrong": 0,
        }

    return statistics[user_id]


# ---------------------------------------------------------
# Тест
# ---------------------------------------------------------

def get_question():
    """Generate random question."""

    question = random.choice(WORDS)
    correct_answer = question["russian"]

    other_words = [
        word
        for word in WORDS
        if word["russian"] != correct_answer
    ]

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


async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_question(update.effective_chat.id, context)


async def send_question(chat_id, context):

    question, answers = get_question()

    # Сохраняем текущий вопрос
    context.user_data["current_question"] = {
        "kazakh": question["kazakh"],
        "correct": question["russian"],
        "answers": answers,
    }

    buttons = []

    for index, answer_text in enumerate(answers):
        buttons.append([
            InlineKeyboardButton(
                answer_text,
                callback_data=f"answer:{index}"
            )
        ])

    keyboard = InlineKeyboardMarkup(buttons)

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            f"🇰🇿 <b>{question['kazakh']}</b>\n\n"
            f"Выберите перевод:"
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    question = context.user_data.get("current_question")

    if not question:
        await query.edit_message_text(
            "Вопрос устарел. Нажмите /quiz, чтобы начать новый тест."
        )
        return

    # answer:0 / answer:1 / answer:2 / answer:3
    answer_index = int(query.data.split(":")[1])

    selected_answer = question["answers"][answer_index]
    correct_answer = question["correct"]

    stats = get_statistics(update.effective_user.id)

    stats["total"] += 1

    if selected_answer == correct_answer:

        stats["correct"] += 1

        result = "✅ <b>Правильно!</b>"

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
                "📖 Словарь",
                callback_data="dictionary:0"
            ),
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

    query = update.callback_query
    await query.answer()

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


# ---------------------------------------------------------
# Статистика
# ---------------------------------------------------------

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    user_stats = get_statistics(user_id)

    total = user_stats["total"]
    correct = user_stats["correct"]
    wrong = user_stats["wrong"]

    percentage = (
        correct / total * 100
        if total
        else 0
    )

    text = (
        "📊 <b>Твоя статистика</b>\n\n"
        f"Всего вопросов: <b>{total}</b>\n"
        f"Правильных: <b>{correct}</b>\n"
        f"Неправильных: <b>{wrong}</b>\n"
        f"Результат: <b>{percentage:.1f}%</b>"
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
                "📖 Словарь",
                callback_data="dictionary:0"
            )
        ]
    ])

    if update.callback_query:

        query = update.callback_query

        await query.answer()

        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    else:

        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ---------------------------------------------------------
# Словарь
# ---------------------------------------------------------

WORDS_PER_PAGE = 15


async def dictionary(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    if query:
        await query.answer()

        # dictionary:0
        page = int(query.data.split(":")[1])

        await show_dictionary(
            query.message.chat_id,
            page,
            context,
            message=query.message
        )

    else:

        await show_dictionary(
            update.effective_chat.id,
            0,
            context
        )


async def show_dictionary(
    chat_id,
    page,
    context,
    message=None
):

    total_words = len(WORDS)

    total_pages = math.ceil(
        total_words / WORDS_PER_PAGE
    )

    # Защита от выхода за пределы
    page = max(
        0,
        min(page, total_pages - 1)
    )

    start = page * WORDS_PER_PAGE
    end = min(
        start + WORDS_PER_PAGE,
        total_words
    )

    page_words = WORDS[start:end]

    text_lines = [
        f"📖 <b>Словарь</b>  •  страница {page + 1}/{total_pages}",
        ""
    ]

    for index, word in enumerate(page_words, start=start + 1):

        text_lines.append(
            f"<b>{index}.</b> "
            f"{word['kazakh']} — {word['russian']}"
        )

    text = "\n".join(text_lines)

    buttons = []

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                "⬅️ Предыдущие",
                callback_data=f"dictionary:{page - 1}"
            )
        )

    if page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                "Следующие ➡️",
                callback_data=f"dictionary:{page + 1}"
            )
        )

    if navigation:
        buttons.append(navigation)

    buttons.append([
        InlineKeyboardButton(
            "🎯 К тесту",
            callback_data="next"
        ),
        InlineKeyboardButton(
            "📊 Статистика",
            callback_data="stats"
        ),
    ])

    keyboard = InlineKeyboardMarkup(buttons)

    if message:

        await message.edit_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    else:

        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ---------------------------------------------------------
# /start
# ---------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🎯 Начать тест",
                callback_data="next"
            )
        ],
        [
            InlineKeyboardButton(
                "📖 Словарь",
                callback_data="dictionary:0"
            )
        ],
        [
            InlineKeyboardButton(
                "📊 Статистика",
                callback_data="stats"
            )
        ],
    ])

    await update.message.reply_text(
        "Привет! Я бот для изучения казахского языка.\n\n"
        "Выбери режим:",
        reply_markup=keyboard
    )


# ---------------------------------------------------------
# Обработчик кнопок
# ---------------------------------------------------------

async def button_handler(update, context):

    query = update.callback_query

    if query.data.startswith("answer:"):
        await answer(update, context)

    elif query.data == "next":
        await next_question(update, context)

    elif query.data == "stats":
        await stats(update, context)

    elif query.data.startswith("dictionary:"):
        await dictionary(update, context)


# ---------------------------------------------------------
# Запуск
# ---------------------------------------------------------

def main():

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

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
        CommandHandler("dictionary", dictionary)
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
