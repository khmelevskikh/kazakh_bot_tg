```python
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

def get_statistics(user_id, context):

    if "statistics" not in context.user_data:

        context.user_data["statistics"] = {
            "total": 0,
            "correct": 0,
            "wrong": 0,
        }

    return context.user_data["statistics"]


# ---------------------------------------------------------
# Ошибки пользователя
# ---------------------------------------------------------

def get_mistakes(context):

    if "mistakes" not in context.user_data:
        context.user_data["mistakes"] = {}

    return context.user_data["mistakes"]


def add_mistake(context, word):

    mistakes = get_mistakes(context)

    key = word["kazakh"]

    if key not in mistakes:

        mistakes[key] = {
            "kazakh": word["kazakh"],
            "russian": word["russian"],
            "wrong": 0,
        }

    mistakes[key]["wrong"] += 1


def remove_mistake(context, word):

    mistakes = get_mistakes(context)

    key = word["kazakh"]

    if key not in mistakes:
        return

    mistakes[key]["wrong"] -= 1

    if mistakes[key]["wrong"] <= 0:
        del mistakes[key]


# ---------------------------------------------------------
# Получение слова для теста
# ---------------------------------------------------------

def get_question(context):

    quiz_mode = context.user_data.get(
        "quiz_mode",
        "all"
    )

    # ---------------------------------------------
    # Режим тренировки ошибок
    # ---------------------------------------------

    if quiz_mode == "errors":

        mistakes = get_mistakes(context)

        if mistakes:

            mistake_words = list(
                mistakes.values()
            )

            # Чем больше ошибок,
            # тем выше вероятность выбрать слово.
            weights = [
                max(1, word["wrong"])
                for word in mistake_words
            ]

            question = random.choices(
                mistake_words,
                weights=weights,
                k=1
            )[0]

        else:

            # Если ошибок больше нет,
            # возвращаемся к обычному режиму.
            context.user_data["quiz_mode"] = "all"

            question = random.choice(WORDS)

    # ---------------------------------------------
    # Обычный режим
    # ---------------------------------------------

    else:

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


# ---------------------------------------------------------
# Отправка вопроса
# ---------------------------------------------------------

async def send_question(chat_id, context):

    question, answers = get_question(context)

    # Сохраняем текущий вопрос
    context.user_data["current_question"] = {

        "kazakh": question["kazakh"],

        "correct": question["russian"],

        "answers": answers,

        "mode": context.user_data.get(
            "quiz_mode",
            "all"
        ),
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

    mode = context.user_data.get(
        "quiz_mode",
        "all"
    )

    if mode == "errors":

        title = "📚 <b>Тренировка ошибок</b>"

    else:

        title = "🎯 <b>Тест</b>"

    await context.bot.send_message(

        chat_id=chat_id,

        text=(
            f"{title}\n\n"
            f"🇰🇿 <b>{question['kazakh']}</b>\n\n"
            f"Выберите перевод:"
        ),

        reply_markup=keyboard,

        parse_mode="HTML",
    )


# ---------------------------------------------------------
# /quiz
# ---------------------------------------------------------

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["quiz_mode"] = "all"

    await send_question(
        update.effective_chat.id,
        context
    )


# ---------------------------------------------------------
# Ответ
# ---------------------------------------------------------

async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    question = context.user_data.get(
        "current_question"
    )

    if not question:

        await query.edit_message_text(
            "Вопрос устарел. Нажмите /quiz, чтобы начать новый тест."
        )

        return

    try:

        answer_index = int(
            query.data.split(":")[1]
        )

        selected_answer = question["answers"][
            answer_index
        ]

    except (ValueError, IndexError):

        await query.edit_message_text(
            "Эта кнопка больше недействительна. "
            "Запустите новый тест."
        )

        return

    correct_answer = question["correct"]

    stats = get_statistics(
        update.effective_user.id,
        context
    )

    stats["total"] += 1

    word = {
        "kazakh": question["kazakh"],
        "russian": correct_answer,
    }

    # ---------------------------------------------
    # Правильный ответ
    # ---------------------------------------------

    if selected_answer == correct_answer:

        stats["correct"] += 1

        remove_mistake(
            context,
            word
        )

        result = "✅ <b>Правильно!</b>"

    # ---------------------------------------------
    # Ошибка
    # ---------------------------------------------

    else:

        stats["wrong"] += 1

        add_mistake(
            context,
            word
        )

        mistakes = get_mistakes(context)

        error_count = mistakes[
            question["kazakh"]
        ]["wrong"]

        result = (
            "❌ <b>Неправильно.</b>\n\n"
            f"Правильный ответ: "
            f"<b>{correct_answer}</b>\n\n"
            f"Ошибок по этому слову: "
            f"<b>{error_count}</b>"
        )

    # ---------------------------------------------
    # Кнопки
    # ---------------------------------------------

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
                "📚 Мои ошибки",
                callback_data="mistakes"
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


# ---------------------------------------------------------
# Следующий вопрос
# ---------------------------------------------------------

async def next_question(update, context):

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

async def stats(update, context):

    user_id = update.effective_user.id

    user_stats = get_statistics(
        user_id,
        context
    )

    total = user_stats["total"]

    correct = user_stats["correct"]

    wrong = user_stats["wrong"]

    percentage = (
        correct / total * 100
        if total
        else 0
    )

    mistakes = get_mistakes(context)

    text = (

        "📊 <b>Твоя статистика</b>\n\n"

        f"Всего вопросов: "
        f"<b>{total}</b>\n"

        f"Правильных: "
        f"<b>{correct}</b>\n"

        f"Неправильных: "
        f"<b>{wrong}</b>\n"

        f"Результат: "
        f"<b>{percentage:.1f}%</b>\n\n"

        f"📚 Слов с ошибками: "
        f"<b>{len(mistakes)}</b>"
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
                "📚 Мои ошибки",
                callback_data="mistakes"
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
# Мои ошибки
# ---------------------------------------------------------

async def mistakes(update, context):

    query = update.callback_query

    if query:

        await query.answer()

    mistakes_data = get_mistakes(context)

    if not mistakes_data:

        text = (
            "📚 <b>Мои ошибки</b>\n\n"
            "🎉 Пока ошибок нет!\n\n"
            "Продолжай проходить тест."
        )

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
            ]

        ])

    else:

        # Сортируем по количеству ошибок
        words = sorted(
            mistakes_data.values(),
            key=lambda x: x["wrong"],
            reverse=True
        )

        text_lines = [
            "📚 <b>Мои ошибки</b>",
            "",
            f"Всего слов: <b>{len(words)}</b>",
            "",
        ]

        for index, word in enumerate(
            words,
            start=1
        ):

            text_lines.append(

                f"<b>{index}.</b> "
                f"🇰🇿 {word['kazakh']} "
                f"— {word['russian']} "
                f"❌ {word['wrong']}"
            )

        text = "\n".join(text_lines)

        keyboard = InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🎯 Тренировать ошибки",
                    callback_data="mistakes_quiz"
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
            ]

        ])

    if query:

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
# Тренировка ошибок
# ---------------------------------------------------------

async def mistakes_quiz(update, context):

    query = update.callback_query

    await query.answer()

    mistakes_data = get_mistakes(context)

    if not mistakes_data:

        await query.edit_message_text(
            "🎉 Ошибок больше нет!"
        )

        return

    context.user_data["quiz_mode"] = "errors"

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


# ---------------------------------------------------------
# Словарь
# ---------------------------------------------------------

WORDS_PER_PAGE = 15


async def dictionary(update, context):

    query = update.callback_query

    if query:

        await query.answer()

        page = int(
            query.data.split(":")[1]
        )

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

    if total_pages == 0:

        text = "📖 Словарь пуст."

        if message:
            await message.edit_text(text)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text
            )

        return

    page = max(
        0,
        min(
            page,
            total_pages - 1
        )
    )

    start = page * WORDS_PER_PAGE

    end = min(
        start + WORDS_PER_PAGE,
        total_words
    )

    page_words = WORDS[start:end]

    text_lines = [

        f"📖 <b>Словарь</b>  •  "
        f"страница {page + 1}/{total_pages}",

        ""

    ]

    for index, word in enumerate(
        page_words,
        start=start + 1
    ):

        text_lines.append(

            f"<b>{index}.</b> "
            f"{word['kazakh']} — "
            f"{word['russian']}"
        )

    text = "\n".join(text_lines)

    buttons = []

    navigation = []

    if page > 0:

        navigation.append(

            InlineKeyboardButton(

                "⬅️ Предыдущие",

                callback_data=(
                    f"dictionary:{page - 1}"
                )
            )
        )

    if page < total_pages - 1:

        navigation.append(

            InlineKeyboardButton(

                "Следующие ➡️",

                callback_data=(
                    f"dictionary:{page + 1}"
                )
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
            "📚 Мои ошибки",
            callback_data="mistakes"
        )

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

async def start(update, context):

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
                "📚 Мои ошибки",
                callback_data="mistakes"
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

        "Привет! Я бот для изучения "
        "казахского языка.\n\n"
        "Выбери режим:",

        reply_markup=keyboard
    )


# ---------------------------------------------------------
# Обработчик кнопок
# ---------------------------------------------------------

async def button_handler(update, context):

    query = update.callback_query

    data = query.data

    if data.startswith("answer:"):

        await answer(
            update,
            context
        )

    elif data == "next":

        await next_question(
            update,
            context
        )

    elif data == "stats":

        await stats(
            update,
            context
        )

    elif data.startswith("dictionary:"):

        await dictionary(
            update,
            context
        )

    elif data == "mistakes":

        await mistakes(
            update,
            context
        )

    elif data == "mistakes_quiz":

        await mistakes_quiz(
            update,
            context
        )


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
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "quiz",
            quiz
        )
    )

    application.add_handler(
        CommandHandler(
            "stats",
            stats
        )
    )

    application.add_handler(
        CommandHandler(
            "dictionary",
            dictionary
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    application.run_webhook(

        listen="0.0.0.0",

        port=PORT,

        webhook_url=(
            f"{PUBLIC_URL}/telegram"
        ),

        url_path="telegram",
    )


if __name__ == "__main__":
    main()
```
