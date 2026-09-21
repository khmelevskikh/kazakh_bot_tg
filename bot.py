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
    MessageHandler,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.environ["TELEGRAM_TOKEN"]
PORT = int(os.environ.get("PORT", "10000"))
PUBLIC_URL = os.environ["RENDER_EXTERNAL_URL"]
ADMIN_ID = int(os.environ["TELEGRAM_ADMIN_ID"])

WORDS_TO_LEARN = 5
WORDS_PER_PAGE = 15

QUIZ_MODE_KK_RU = "kk_ru"
QUIZ_MODE_RU_KK = "ru_kk"
QUIZ_MODE_ERRORS = "errors"
QUIZ_MODE_PAGE = "page"


# ============================================================
# WORDS
# ============================================================

def load_words(filename):
    words = []

    with open(filename, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if not line.startswith("|"):
                continue

            parts = [x.strip() for x in line.strip("|").split("|")]

            if len(parts) < 2:
                continue

            kazakh = parts[0]
            russian = parts[1]

            # Skip markdown header/separator
            if (
                not kazakh
                or not russian
                or kazakh.lower() in ("казахское", "казахский")
                or russian.lower() in ("русский перевод", "русский")
                or re.fullmatch(r"[-: ]+", kazakh)
                or re.fullmatch(r"[-: ]+", russian)
            ):
                continue

            words.append({
                "kazakh": kazakh,
                "russian": russian,
            })

    return words


WORDS = load_words("words.md")


# ============================================================
# USERS
# ============================================================

users = set()


def register_user(user_id):
    users.add(user_id)


# ============================================================
# STATISTICS
# ============================================================

def get_statistics(context):
    if "statistics" not in context.user_data:
        context.user_data["statistics"] = {
            "total": 0,
            "correct": 0,
            "wrong": 0,
        }

    return context.user_data["statistics"]


# ============================================================
# WORD PROGRESS
# ============================================================

def get_word_progress(context):
    if "word_progress" not in context.user_data:
        context.user_data["word_progress"] = {}

    return context.user_data["word_progress"]


def get_word_progress_value(context, kazakh):
    progress = get_word_progress(context)
    return progress.get(kazakh, 0)


def increase_word_progress(context, kazakh):
    progress = get_word_progress(context)

    current = progress.get(kazakh, 0)

    if current < WORDS_TO_LEARN:
        current += 1

    progress[kazakh] = current

    return current


def reset_word_progress(context, kazakh):
    progress = get_word_progress(context)
    progress[kazakh] = 0


# ============================================================
# MISTAKES
# ============================================================

def get_mistakes(context):
    if "mistakes" not in context.user_data:
        context.user_data["mistakes"] = {}

    return context.user_data["mistakes"]


def add_mistake(context, word):
    mistakes = get_mistakes(context)

    kazakh = word["kazakh"]

    if kazakh not in mistakes:
        mistakes[kazakh] = {
            "kazakh": word["kazakh"],
            "russian": word["russian"],
            "wrong": 0,
        }

    mistakes[kazakh]["wrong"] += 1


def remove_mistake(context, kazakh):
    mistakes = get_mistakes(context)

    if kazakh not in mistakes:
        return

    mistakes[kazakh]["wrong"] -= 1

    if mistakes[kazakh]["wrong"] <= 0:
        del mistakes[kazakh]


# ============================================================
# PAGE HELPERS
# ============================================================

def get_total_pages():
    if not WORDS:
        return 0

    return math.ceil(len(WORDS) / WORDS_PER_PAGE)


def get_page_words(page):
    """
    page = zero-based page number
    """

    start = page * WORDS_PER_PAGE
    end = start + WORDS_PER_PAGE

    return WORDS[start:end]


def get_page_number(context):
    page = context.user_data.get("page_quiz_page")

    if page is None:
        return None

    return page + 1


# ============================================================
# NORMAL QUIZ QUESTION
# ============================================================

def get_normal_question(context, mode):

    # --------------------------------------------------------
    # Page training
    # --------------------------------------------------------

    if mode == QUIZ_MODE_PAGE:

        page = context.user_data.get("page_quiz_page")

        if page is None:
            return None

        source_words = get_page_words(page)

        direction = context.user_data.get(
            "page_quiz_direction",
            QUIZ_MODE_KK_RU
        )

    # --------------------------------------------------------
    # Normal full dictionary
    # --------------------------------------------------------

    else:
        source_words = WORDS
        direction = mode

    # Only words that are not yet learned
    available = [
        word
        for word in source_words
        if get_word_progress_value(
            context,
            word["kazakh"]
        ) < WORDS_TO_LEARN
    ]

    if not available:
        return None

    word = random.choice(available)

    # --------------------------------------------------------
    # Kazakh -> Russian
    # --------------------------------------------------------

    if direction == QUIZ_MODE_KK_RU:

        correct = word["russian"]

        other_words = [
            w["russian"]
            for w in source_words
            if w["kazakh"] != word["kazakh"]
        ]

        random.shuffle(other_words)

        options = [correct] + other_words[:3]
        random.shuffle(options)

        return {
            "word": word,
            "question": word["kazakh"],
            "correct": correct,
            "options": options,
            "direction": QUIZ_MODE_KK_RU,
        }

    # --------------------------------------------------------
    # Russian -> Kazakh
    # --------------------------------------------------------

    else:

        correct = word["kazakh"]

        other_words = [
            w["kazakh"]
            for w in source_words
            if w["kazakh"] != word["kazakh"]
        ]

        random.shuffle(other_words)

        options = [correct] + other_words[:3]
        random.shuffle(options)

        return {
            "word": word,
            "question": word["russian"],
            "correct": correct,
            "options": options,
            "direction": QUIZ_MODE_RU_KK,
        }


# ============================================================
# ERROR QUESTION
# ============================================================

def get_error_question(context):

    mistakes = get_mistakes(context)

    if not mistakes:
        return None

    weighted = []

    for mistake in mistakes.values():

        count = max(1, mistake["wrong"])

        for _ in range(count):
            weighted.append(mistake)

    if not weighted:
        return None

    mistake = random.choice(weighted)

    word = {
        "kazakh": mistake["kazakh"],
        "russian": mistake["russian"],
    }

    correct = word["russian"]

    other_words = [
        w["russian"]
        for w in WORDS
        if w["kazakh"] != word["kazakh"]
    ]

    random.shuffle(other_words)

    options = [correct] + other_words[:3]
    random.shuffle(options)

    return {
        "word": word,
        "question": word["kazakh"],
        "correct": correct,
        "options": options,
        "direction": QUIZ_MODE_KK_RU,
    }


# ============================================================
# GET QUESTION
# ============================================================

def get_question(context, mode):

    if mode == QUIZ_MODE_ERRORS:
        return get_error_question(context)

    return get_normal_question(context, mode)


# ============================================================
# MODE TITLE
# ============================================================

def get_mode_title(context, mode):

    if mode == QUIZ_MODE_KK_RU:
        return "🇰🇿 → 🇷🇺"

    if mode == QUIZ_MODE_RU_KK:
        return "🇷🇺 → 🇰🇿"

    if mode == QUIZ_MODE_ERRORS:
        return "📚 Тренировка ошибок"

    if mode == QUIZ_MODE_PAGE:

        page = get_page_number(context)

        direction = context.user_data.get(
            "page_quiz_direction",
            QUIZ_MODE_KK_RU
        )

        if direction == QUIZ_MODE_KK_RU:
            direction_text = "🇰🇿 → 🇷🇺"
        else:
            direction_text = "🇷🇺 → 🇰🇿"

        return f"📄 Страница {page} • {direction_text}"

    return "🎯 Тест"


# ============================================================
# SEND QUESTION
# ============================================================

async def send_question(chat_id, context):

    mode = context.user_data.get(
        "quiz_mode",
        QUIZ_MODE_KK_RU
    )

    question = get_question(context, mode)

    # --------------------------------------------------------
    # No questions left
    # --------------------------------------------------------

    if question is None:

        if mode == QUIZ_MODE_ERRORS:

            keyboard = [
                [
                    InlineKeyboardButton(
                        "🎯 Вернуться к тесту",
                        callback_data="quiz_menu"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❗ Мои ошибки",
                        callback_data="mistakes"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📖 Словарь",
                        callback_data="dictionary:0"
                    )
                ],
            ]

            await context.bot.send_message(
                chat_id=chat_id,
                text="🎉 Все ошибки исправлены!",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

            return

        if mode == QUIZ_MODE_PAGE:

            page = get_page_number(context)

            keyboard = [
                [
                    InlineKeyboardButton(
                        "🎯 Вернуться к тесту",
                        callback_data="quiz_menu"
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
                        "◀️ Главное меню",
                        callback_data="start_menu"
                    )
                ],
            ]

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"🎉 Страница {page} полностью выучена!\n\n"
                    f"Все слова этой страницы имеют прогресс "
                    f"{WORDS_TO_LEARN}/{WORDS_TO_LEARN}."
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

            return

        # Normal test

        keyboard = [
            [
                InlineKeyboardButton(
                    "🔄 Повторить все",
                    callback_data="repeat_all"
                )
            ],
            [
                InlineKeyboardButton(
                    "📚 Тренировать ошибки",
                    callback_data="quiz_errors"
                )
            ],
            [
                InlineKeyboardButton(
                    "❗ Мои ошибки",
                    callback_data="mistakes"
                )
            ],
            [
                InlineKeyboardButton(
                    "📖 Словарь",
                    callback_data="dictionary:0"
                )
            ],
        ]

        await context.bot.send_message(
            chat_id=chat_id,
            text="🎉 Все слова выучены!",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

        return

    # Save current question
    context.user_data["current_question"] = question

    word = question["word"]
    progress = get_word_progress_value(
        context,
        word["kazakh"]
    )

    mode_title = get_mode_title(context, mode)

    # --------------------------------------------------------
    # Progress
    # --------------------------------------------------------

    if mode == QUIZ_MODE_ERRORS:

        mistakes = get_mistakes(context)

        total_errors = sum(
            item["wrong"]
            for item in mistakes.values()
        )

        progress_text = f"Ошибок осталось: {total_errors}"

    else:

        progress_text = (
            f"Прогресс слова: "
            f"{progress}/{WORDS_TO_LEARN}"
        )

    text = (
        f"{mode_title}\n\n"
        f"{progress_text}\n\n"
        f"❓ <b>{question['question']}</b>"
    )

    keyboard = []

    for index, option in enumerate(question["options"]):

        keyboard.append([
            InlineKeyboardButton(
                option,
                callback_data=f"answer:{index}"
            )
        ])

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# QUIZ MENU
# ============================================================

async def show_quiz_menu(
    update,
    context,
    edit_message=False
):

    text = (
        "🎯 <b>Тест</b>\n\n"
        "Выбери режим:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🇰🇿 → 🇷🇺",
                callback_data="quiz_kk_ru"
            ),
            InlineKeyboardButton(
                "🇷🇺 → 🇰🇿",
                callback_data="quiz_ru_kk"
            ),
        ],
        [
            InlineKeyboardButton(
                "📄 Тренировать страницу",
                callback_data="page_quiz"
            )
        ],
        [
            InlineKeyboardButton(
                "📚 Тренировка ошибок",
                callback_data="quiz_errors"
            )
        ],
        [
            InlineKeyboardButton(
                "❗ Мои ошибки",
                callback_data="mistakes"
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
                "◀️ Назад",
                callback_data="start_menu"
            )
        ],
    ]

    markup = InlineKeyboardMarkup(keyboard)

    if edit_message:

        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )

    else:

        await update.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )

# ============================================================
# QUIZ COMMAND
# ============================================================

async def quiz_command(update, context):

    register_user(update.effective_user.id)

    await show_quiz_menu(
        update,
        context,
        edit_message=False
    )


# ============================================================
# START QUIZ
# ============================================================

async def start_quiz(update, context, mode):

    query = update.callback_query
    await query.answer()

    context.user_data["quiz_mode"] = mode

    context.user_data["waiting_dictionary_page"] = False
    context.user_data["waiting_page_quiz_page"] = False

    try:
        await query.message.delete()
    except Exception:
        pass

    await send_question(
        query.message.chat_id,
        context
    )


# ============================================================
# PAGE QUIZ MENU
# ============================================================

async def show_page_quiz_direction(
    update,
    context,
    page,
    edit_message=True
):

    context.user_data["page_quiz_page"] = page

    total_pages = get_total_pages()

    text = (
        f"📄 <b>Тренировка страницы {page + 1}</b>\n\n"
        f"На странице {len(get_page_words(page))} слов.\n"
        f"Всего страниц: {total_pages}.\n\n"
        f"Выбери направление:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🇰🇿 → 🇷🇺",
                callback_data="page_quiz_kk_ru"
            )
        ],
        [
            InlineKeyboardButton(
                "🇷🇺 → 🇰🇿",
                callback_data="page_quiz_ru_kk"
            )
        ],
        [
            InlineKeyboardButton(
                "◀️ Назад",
                callback_data="quiz_menu"
            )
        ],
    ]

    markup = InlineKeyboardMarkup(keyboard)

    if edit_message:

        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )

    else:

        await update.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )


# ============================================================
# PAGE QUIZ REQUEST
# ============================================================

async def page_quiz_button(update, context):

    query = update.callback_query
    await query.answer()

    total_pages = get_total_pages()

    context.user_data["waiting_page_quiz_page"] = True
    context.user_data["waiting_dictionary_page"] = False

    keyboard = [
        [
            InlineKeyboardButton(
                "◀️ Назад",
                callback_data="quiz_menu"
            )
        ]
    ]

    await query.edit_message_text(
        text=(
            f"📄 <b>Тренировать страницу</b>\n\n"
            f"Введите номер страницы от "
            f"<b>1</b> до <b>{total_pages}</b>."
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# PAGE QUIZ PAGE NUMBER
# ============================================================

async def page_quiz_page_request(update, context):

    if not context.user_data.get(
        "waiting_page_quiz_page",
        False
    ):
        return

    text = update.message.text.strip()

    total_pages = get_total_pages()

    try:
        page_number = int(text)
    except ValueError:

        await update.message.reply_text(
            f"Введите номер страницы от 1 до {total_pages}."
        )

        return

    if page_number < 1 or page_number > total_pages:

        await update.message.reply_text(
            f"Такой страницы нет.\n"
            f"Введите номер от 1 до {total_pages}."
        )

        return

    page = page_number - 1

    context.user_data["waiting_page_quiz_page"] = False

    await show_page_quiz_direction(
        update,
        context,
        page,
        edit_message=False
    )


# ============================================================
# ANSWER
# ============================================================

async def answer(update, context):

    query = update.callback_query
    await query.answer()

    question = context.user_data.get(
        "current_question"
    )

    if not question:
        return

    try:
        answer_index = int(
            query.data.split(":")[1]
        )
    except (ValueError, IndexError):
        return

    if answer_index >= len(question["options"]):
        return

    selected = question["options"][answer_index]

    word = question["word"]

    correct = question["correct"]

    statistics = get_statistics(context)

    statistics["total"] += 1

    is_correct = selected == correct

    mode = context.user_data.get(
        "quiz_mode",
        QUIZ_MODE_KK_RU
    )

    # ========================================================
    # CORRECT
    # ========================================================

    if is_correct:

        statistics["correct"] += 1

        # ----------------------------------------------------
        # Error training
        # ----------------------------------------------------

        if mode == QUIZ_MODE_ERRORS:

            remove_mistake(
                context,
                word["kazakh"]
            )

            mistakes = get_mistakes(context)

            remaining = sum(
                item["wrong"]
                for item in mistakes.values()
            )

            if remaining > 0:

                result_text = (
                    "✅ <b>Правильно!</b>\n\n"
                    f"{word['kazakh']} — "
                    f"{word['russian']}\n\n"
                    f"Ошибок осталось: {remaining}"
                )

            else:

                result_text = (
                    "🎉 <b>Все ошибки исправлены!</b>\n\n"
                    f"{word['kazakh']} — "
                    f"{word['russian']}"
                )

        # ----------------------------------------------------
        # Normal / page training
        # ----------------------------------------------------

        else:

            progress = increase_word_progress(
                context,
                word["kazakh"]
            )

            remove_mistake(
                context,
                word["kazakh"]
            )

            if progress >= WORDS_TO_LEARN:

                result_text = (
                    "🎉 <b>Слово выучено!</b>\n\n"
                    f"{word['kazakh']} — "
                    f"{word['russian']}\n\n"
                    f"Прогресс: "
                    f"{WORDS_TO_LEARN}/{WORDS_TO_LEARN}"
                )

            else:

                result_text = (
                    "✅ <b>Правильно!</b>\n\n"
                    f"{word['kazakh']} — "
                    f"{word['russian']}\n\n"
                    f"Прогресс: "
                    f"{progress}/{WORDS_TO_LEARN}"
                )

    # ========================================================
    # WRONG
    # ========================================================

    else:

        statistics["wrong"] += 1

        reset_word_progress(
            context,
            word["kazakh"]
        )

        add_mistake(
            context,
            word
        )

        mistake_count = get_mistakes(
            context
        )[word["kazakh"]]["wrong"]

        result_text = (
            "❌ <b>Неправильно</b>\n\n"
            f"Твой ответ: {selected}\n"
            f"Правильный ответ: <b>{correct}</b>\n\n"
            f"{word['kazakh']} — "
            f"{word['russian']}\n\n"
            f"Ошибок по этому слову: "
            f"{mistake_count}"
        )

    # ========================================================
    # BUTTONS
    # ========================================================

    keyboard = []

    if mode == QUIZ_MODE_ERRORS:

        keyboard.append([
            InlineKeyboardButton(
                "➡️ Следующая ошибка",
                callback_data="next_error"
            )
        ])

        keyboard.append([
            InlineKeyboardButton(
                "🎯 Вернуться к тесту",
                callback_data="quiz_menu"
            )
        ])

    else:

        keyboard.append([
            InlineKeyboardButton(
                "➡️ Следующее слово",
                callback_data="next"
            )
        ])

        if mode != QUIZ_MODE_PAGE:

            keyboard.append([
                InlineKeyboardButton(
                    "📄 Тренировать страницу",
                    callback_data="page_quiz"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "📚 Тренировать ошибки",
                callback_data="quiz_errors"
            )
        ])

    keyboard.append([
        InlineKeyboardButton(
            "❗ Мои ошибки",
            callback_data="mistakes"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "📖 Словарь",
            callback_data="dictionary:0"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "📊 Статистика",
            callback_data="stats"
        )
    ])

    await query.edit_message_text(
        text=result_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# NEXT QUESTION
# ============================================================

async def next_question(update, context):

    query = update.callback_query
    await query.answer()

    try:
        await query.message.delete()
    except Exception:
        pass

    await send_question(
        query.message.chat_id,
        context
    )


# ============================================================
# NEXT ERROR
# ============================================================

async def next_error(update, context):

    query = update.callback_query
    await query.answer()

    context.user_data["quiz_mode"] = QUIZ_MODE_ERRORS

    try:
        await query.message.delete()
    except Exception:
        pass

    await send_question(
        query.message.chat_id,
        context
    )


# ============================================================
# REPEAT ALL
# ============================================================

async def repeat_all(update, context):

    query = update.callback_query
    await query.answer()

    progress = get_word_progress(context)

    for word in WORDS:
        progress[word["kazakh"]] = 0

    context.user_data["mistakes"] = {}

    context.user_data["quiz_mode"] = QUIZ_MODE_KK_RU

    try:
        await query.message.delete()
    except Exception:
        pass

    await send_question(
        query.message.chat_id,
        context
    )


# ============================================================
# MISTAKES
# ============================================================

async def show_mistakes(update, context):

    query = update.callback_query
    await query.answer()

    mistakes = get_mistakes(context)

    if not mistakes:

        text = "🎉 У тебя сейчас нет ошибок!"

    else:

        sorted_mistakes = sorted(
            mistakes.values(),
            key=lambda x: x["wrong"],
            reverse=True
        )

        lines = [
            "❗ <b>Мои ошибки</b>\n"
        ]

        for index, mistake in enumerate(
            sorted_mistakes,
            start=1
        ):

            lines.append(
                f"{index}. "
                f"{mistake['kazakh']} — "
                f"{mistake['russian']} "
                f"❌ {mistake['wrong']}"
            )

        text = "\n".join(lines)

    keyboard = [
        [
            InlineKeyboardButton(
                "📚 Тренировать ошибки",
                callback_data="quiz_errors"
            )
        ],
        [
            InlineKeyboardButton(
                "🎯 К тесту",
                callback_data="quiz_menu"
            )
        ],
        [
            InlineKeyboardButton(
                "◀️ Назад",
                callback_data="start_menu"
            )
        ],
    ]

    await query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# STATISTICS
# ============================================================

async def show_statistics(update, context):

    query = update.callback_query
    await query.answer()

    statistics = get_statistics(context)

    total = statistics["total"]
    correct = statistics["correct"]
    wrong = statistics["wrong"]

    if total > 0:
        percent = round(
            correct / total * 100
        )
    else:
        percent = 0

    progress = get_word_progress(context)

    learned = sum(
        1
        for word in WORDS
        if progress.get(word["kazakh"], 0)
        >= WORDS_TO_LEARN
    )

    in_progress = sum(
        1
        for word in WORDS
        if 0 < progress.get(
            word["kazakh"],
            0
        ) < WORDS_TO_LEARN
    )

    not_started = len(WORDS) - learned - in_progress

    mistakes = get_mistakes(context)

    text = (
        "📊 <b>Моя статистика</b>\n\n"
        f"Всего ответов: {total}\n"
        f"✅ Правильных: {correct}\n"
        f"❌ Неправильных: {wrong}\n"
        f"🎯 Процент правильных: {percent}%\n\n"
        f"📚 Всего слов: {len(WORDS)}\n"
        f"🎓 Выучено: {learned}\n"
        f"🔄 В процессе: {in_progress}\n"
        f"🆕 Не начато: {not_started}\n"
        f"❗ Слов с ошибками: {len(mistakes)}"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🎯 Тест",
                callback_data="quiz_menu"
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
                "◀️ Назад",
                callback_data="start_menu"
            )
        ],
    ]

    await query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ============================================================
# DICTIONARY
# ============================================================

async def dictionary(update, context):

    if update.callback_query:

        query = update.callback_query
        await query.answer()

        try:
            page = int(
                query.data.split(":")[1]
            )
        except (ValueError, IndexError):
            page = 0

        await show_dictionary(
            query.message.chat_id,
            page,
            context,
            message=query.message
        )

    else:

        await show_dictionary(
            update.message.chat_id,
            0,
            context
        )


# ============================================================
# SHOW DICTIONARY
# ============================================================

async def show_dictionary(
    chat_id,
    page,
    context,
    message=None
):

    total_pages = get_total_pages()

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
        min(page, total_pages - 1)
    )

    page_words = get_page_words(page)

    lines = [
        f"📖 <b>Словарь — страница "
        f"{page + 1}/{total_pages}</b>\n"
    ]

    for index, word in enumerate(
        page_words,
        start=page * WORDS_PER_PAGE + 1
    ):

        progress = get_word_progress_value(
            context,
            word["kazakh"]
        )

        if progress >= WORDS_TO_LEARN:
            status = "🎓"

        elif progress > 0:
            status = f"🔄 {progress}/{WORDS_TO_LEARN}"

        else:
            status = "🆕"

        lines.append(
            f"{index}. {status} "
            f"<b>{word['kazakh']}</b> — "
            f"{word['russian']}"
        )

    text = "\n".join(lines)

    keyboard = []

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
        keyboard.append(navigation)

    keyboard.append([
        InlineKeyboardButton(
            "🔢 Перейти на страницу",
            callback_data="dictionary_page"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "📄 Тренировать эту страницу",
            callback_data=f"page_train:{page}"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "🎯 Тест",
            callback_data="quiz_menu"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "❗ Мои ошибки",
            callback_data="mistakes"
        )
    ])

    keyboard.append([
        InlineKeyboardButton(
            "◀️ Назад",
            callback_data="start_menu"
        )
    ])

    markup = InlineKeyboardMarkup(keyboard)

    if message:

        await message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )

    else:

        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )


# ============================================================
# DICTIONARY PAGE BUTTON
# ============================================================

async def dictionary_page_button(
    update,
    context
):

    query = update.callback_query
    await query.answer()

    total_pages = get_total_pages()

    context.user_data[
        "waiting_dictionary_page"
    ] = True

    context.user_data[
        "waiting_page_quiz_page"
    ] = False

    await query.edit_message_text(
        text=(
            f"🔢 <b>Перейти на страницу</b>\n\n"
            f"Введите номер страницы от "
            f"<b>1</b> до <b>{total_pages}</b>."
        ),
        parse_mode="HTML",
    )


# ============================================================
# DICTIONARY PAGE REQUEST
# ============================================================

async def dictionary_page_request(
    update,
    context
):

    if not context.user_data.get(
        "waiting_dictionary_page",
        False
    ):
        return

    text = update.message.text.strip()

    total_pages = get_total_pages()

    try:
        page_number = int(text)

    except ValueError:

        await update.message.reply_text(
            f"Введите номер страницы от 1 до {total_pages}."
        )

        return

    if page_number < 1 or page_number > total_pages:

        await update.message.reply_text(
            f"Такой страницы нет.\n"
            f"Введите номер от 1 до {total_pages}."
        )

        return

    context.user_data[
        "waiting_dictionary_page"
    ] = False

    await show_dictionary(
        update.message.chat_id,
        page_number - 1,
        context
    )


# ============================================================
# PAGE TRAIN FROM DICTIONARY
# ============================================================

async def train_current_page(
    update,
    context
):

    query = update.callback_query
    await query.answer()

    try:
        page = int(
            query.data.split(":")[1]
        )
    except (ValueError, IndexError):
        return

    context.user_data[
        "waiting_dictionary_page"
    ] = False

    context.user_data[
        "waiting_page_quiz_page"
    ] = False

    await show_page_quiz_direction(
        update,
        context,
        page,
        edit_message=True
    )


# ============================================================
# START MENU
# ============================================================

async def show_start_menu(
    update,
    context,
    edit_message=False
):

    text = (
        "🇰🇿 <b>Изучение казахского языка</b>\n\n"
        "Выбери действие:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🎯 Тест",
                callback_data="quiz_menu"
            )
        ],
        [
            InlineKeyboardButton(
                "📄 Тренировать страницу",
                callback_data="page_quiz"
            )
        ],
        [
            InlineKeyboardButton(
                "📚 Тренировка ошибок",
                callback_data="quiz_errors"
            )
        ],
        [
            InlineKeyboardButton(
                "❗ Мои ошибки",
                callback_data="mistakes"
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
    ]

    markup = InlineKeyboardMarkup(keyboard)

    if edit_message:

        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )

    else:

        await update.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup,
        )


# ============================================================
# START
# ============================================================

async def start(update, context):

    register_user(update.effective_user.id)

    context.user_data[
        "waiting_dictionary_page"
    ] = False

    context.user_data[
        "waiting_page_quiz_page"
    ] = False

    await show_start_menu(
        update,
        context,
        edit_message=False
    )


# ============================================================
# ADMIN USERS
# ============================================================

async def users_command(update, context):

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:

        await update.message.reply_text(
            "⛔ Доступ запрещён."
        )

        return

    await update.message.reply_text(
        f"👥 Пользователей: {len(users)}"
    )


# ============================================================
# BUTTON HANDLER
# ============================================================

async def button_handler(
    update,
    context
):

    query = update.callback_query

    data = query.data

    # --------------------------------------------------------
    # Start menu
    # --------------------------------------------------------

    if data == "start_menu":

        context.user_data[
            "waiting_dictionary_page"
        ] = False

        context.user_data[
            "waiting_page_quiz_page"
        ] = False

        await query.answer()

        await show_start_menu(
            update,
            context,
            edit_message=True
        )

        return

    # --------------------------------------------------------
    # Quiz menu
    # --------------------------------------------------------

    if data == "quiz_menu":

        context.user_data[
            "waiting_dictionary_page"
        ] = False

        context.user_data[
            "waiting_page_quiz_page"
        ] = False

        await query.answer()

        await show_quiz_menu(
            update,
            context,
            edit_message=True
        )

        return

    # --------------------------------------------------------
    # Normal KK -> RU
    # --------------------------------------------------------

    if data == "quiz_kk_ru":

        await start_quiz(
            update,
            context,
            QUIZ_MODE_KK_RU
        )

        return

    # --------------------------------------------------------
    # Normal RU -> KK
    # --------------------------------------------------------

    if data == "quiz_ru_kk":

        await start_quiz(
            update,
            context,
            QUIZ_MODE_RU_KK
        )

        return

    # --------------------------------------------------------
    # Error training
    # --------------------------------------------------------

    if data == "quiz_errors":

        await start_quiz(
            update,
            context,
            QUIZ_MODE_ERRORS
        )

        return

    # --------------------------------------------------------
    # Page training
    # --------------------------------------------------------

    if data == "page_quiz":

        await page_quiz_button(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Page direction KK -> RU
    # --------------------------------------------------------

    if data == "page_quiz_kk_ru":

        await query.answer()

        context.user_data[
            "quiz_mode"
        ] = QUIZ_MODE_PAGE

        context.user_data[
            "page_quiz_direction"
        ] = QUIZ_MODE_KK_RU

        context.user_data[
            "waiting_page_quiz_page"
        ] = False

        try:
            await query.message.delete()
        except Exception:
            pass

        await send_question(
            query.message.chat_id,
            context
        )

        return

    # --------------------------------------------------------
    # Page direction RU -> KK
    # --------------------------------------------------------

    if data == "page_quiz_ru_kk":

        await query.answer()

        context.user_data[
            "quiz_mode"
        ] = QUIZ_MODE_PAGE

        context.user_data[
            "page_quiz_direction"
        ] = QUIZ_MODE_RU_KK

        context.user_data[
            "waiting_page_quiz_page"
        ] = False

        try:
            await query.message.delete()
        except Exception:
            pass

        await send_question(
            query.message.chat_id,
            context
        )

        return

    # --------------------------------------------------------
    # Answer
    # --------------------------------------------------------

    if data.startswith("answer:"):

        await answer(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Next
    # --------------------------------------------------------

    if data == "next":

        await next_question(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Next error
    # --------------------------------------------------------

    if data == "next_error":

        await next_error(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Repeat all
    # --------------------------------------------------------

    if data == "repeat_all":

        await repeat_all(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    if data == "stats":

        await show_statistics(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Mistakes
    # --------------------------------------------------------

    if data == "mistakes":

        await show_mistakes(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Dictionary
    # --------------------------------------------------------

    if data.startswith("dictionary:"):

        context.user_data[
            "waiting_dictionary_page"
        ] = False

        await dictionary(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Dictionary page input
    # --------------------------------------------------------

    if data == "dictionary_page":

        await dictionary_page_button(
            update,
            context
        )

        return

    # --------------------------------------------------------
    # Train current dictionary page
    # --------------------------------------------------------

    if data.startswith("page_train:"):

        await train_current_page(
            update,
            context
        )

        return


# ============================================================
# MAIN
# ============================================================

def main():

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "quiz",
            quiz_command
        )
    )

    application.add_handler(
        CommandHandler(
            "stats",
            lambda update, context:
                show_statistics(update, context)
        )
    )

    application.add_handler(
        CommandHandler(
            "dictionary",
            dictionary
        )
    )

    application.add_handler(
        CommandHandler(
            "users",
            users_command
        )
    )

    # Page number input
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            page_quiz_page_request
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            dictionary_page_request
        )
    )

    # Buttons
    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # Webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{PUBLIC_URL}/telegram",
        url_path="telegram",
    )


if __name__ == "__main__":
    main()
