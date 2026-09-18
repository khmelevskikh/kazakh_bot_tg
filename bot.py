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


# =========================================================
# Настройки
# =========================================================

TOKEN = os.environ["TELEGRAM_TOKEN"]

PORT = int(
    os.environ.get("PORT", "10000")
)

PUBLIC_URL = os.environ["RENDER_EXTERNAL_URL"]


# Сколько правильных ответов подряд нужно
# для полного изучения слова
WORDS_TO_LEARN = 5

# Сколько слов показывать на странице словаря
WORDS_PER_PAGE = 15


# Режимы теста

QUIZ_MODE_KK_RU = "kk_ru"
QUIZ_MODE_RU_KK = "ru_kk"
QUIZ_MODE_ERRORS = "errors"


# =========================================================
# Загрузка слов
# =========================================================

def load_words(filename):
    """Read words from Markdown table."""

    words = []

    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            # Skip Markdown separator
            if re.match(
                r"^\|\s*-+",
                line
            ):
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

print(
    f"Loaded {len(WORDS)} words"
)


# =========================================================
# Статистика
# =========================================================

def get_statistics(context):

    if "statistics" not in context.user_data:

        context.user_data["statistics"] = {
            "total": 0,
            "correct": 0,
            "wrong": 0,
        }

    return context.user_data["statistics"]


# =========================================================
# Прогресс изучения слов
# =========================================================

def get_word_progress(context):

    if "word_progress" not in context.user_data:

        context.user_data["word_progress"] = {}

    return context.user_data["word_progress"]


def get_word_correct_count(
    context,
    word
):

    progress = get_word_progress(
        context
    )

    return progress.get(
        word["kazakh"],
        0
    )


def increase_word_progress(
    context,
    word
):

    progress = get_word_progress(
        context
    )

    key = word["kazakh"]

    current = progress.get(
        key,
        0
    )

    progress[key] = min(
        current + 1,
        WORDS_TO_LEARN
    )


def reset_word_progress(
    context,
    word
):

    progress = get_word_progress(
        context
    )

    key = word["kazakh"]

    progress[key] = 0


def get_learned_words_count(context):

    progress = get_word_progress(
        context
    )

    return sum(
        1
        for word in WORDS
        if progress.get(
            word["kazakh"],
            0
        ) >= WORDS_TO_LEARN
    )


def get_words_in_progress_count(
    context
):

    progress = get_word_progress(
        context
    )

    return sum(
        1
        for word in WORDS
        if 0 < progress.get(
            word["kazakh"],
            0
        ) < WORDS_TO_LEARN
    )


# =========================================================
# Ошибки пользователя
# =========================================================

def get_mistakes(context):

    if "mistakes" not in context.user_data:

        context.user_data["mistakes"] = {}

    return context.user_data["mistakes"]


def add_mistake(
    context,
    word
):

    mistakes = get_mistakes(
        context
    )

    key = word["kazakh"]

    if key not in mistakes:

        mistakes[key] = {
            "kazakh": word["kazakh"],
            "russian": word["russian"],
            "wrong": 0,
        }

    mistakes[key]["wrong"] += 1


def remove_mistake(
    context,
    word
):

    mistakes = get_mistakes(
        context
    )

    key = word["kazakh"]

    if key not in mistakes:
        return

    mistakes[key]["wrong"] -= 1

    if mistakes[key]["wrong"] <= 0:

        del mistakes[key]


# =========================================================
# Генерация вопроса
# =========================================================

def get_question(context):

    quiz_mode = context.user_data.get(
        "quiz_mode",
        QUIZ_MODE_KK_RU
    )

    # -----------------------------------------------------
    # Режим ошибок
    # -----------------------------------------------------

    if quiz_mode == QUIZ_MODE_ERRORS:

        mistakes = get_mistakes(
            context
        )

        if mistakes:

            mistake_words = list(
                mistakes.values()
            )

            # Чем больше ошибок,
            # тем чаще слово появляется
            weights = [
                max(
                    1,
                    word["wrong"]
                )
                for word in mistake_words
            ]

            question = random.choices(
                mistake_words,
                weights=weights,
                k=1
            )[0]

        else:

            context.user_data[
                "quiz_mode"
            ] = QUIZ_MODE_KK_RU

            question = random.choice(
                WORDS
            )

    # -----------------------------------------------------
    # Обычные режимы
    # -----------------------------------------------------

    else:

        progress = get_word_progress(
            context
        )

        # Берём только слова,
        # которые ещё не изучены
        available_words = [

            word

            for word in WORDS

            if progress.get(
                word["kazakh"],
                0
            ) < WORDS_TO_LEARN

        ]

        if available_words:

            question = random.choice(
                available_words
            )

        else:

            context.user_data[
                "all_words_learned"
            ] = True

            question = random.choice(
                WORDS
            )

    # -----------------------------------------------------
    # Направление перевода
    # -----------------------------------------------------

    if quiz_mode == QUIZ_MODE_RU_KK:

        # Русский вопрос
        question_text = question["russian"]

        # Правильный ответ на казахском
        correct_answer = question["kazakh"]

        # Другие казахские слова
        other_words = [

            word

            for word in WORDS

            if word["kazakh"]
            != correct_answer

        ]

        wrong_answers = random.sample(
            other_words,
            min(
                3,
                len(other_words)
            )
        )

        answers = [
            correct_answer,
            *[
                word["kazakh"]
                for word in wrong_answers
            ]
        ]

    else:

        # Казахский вопрос
        question_text = question["kazakh"]

        # Правильный ответ на русском
        correct_answer = question["russian"]

        # Другие русские переводы
        other_words = [

            word

            for word in WORDS

            if word["russian"]
            != correct_answer

        ]

        wrong_answers = random.sample(
            other_words,
            min(
                3,
                len(other_words)
            )
        )

        answers = [
            correct_answer,
            *[
                word["russian"]
                for word in wrong_answers
            ]
        ]

    random.shuffle(
        answers
    )

    return (
        question,
        question_text,
        answers,
        correct_answer
    )


# =========================================================
# Отправка вопроса
# =========================================================

async def send_question(
    chat_id,
    context
):

    (
        question,
        question_text,
        answers,
        correct_answer
    ) = get_question(
        context
    )

    mode = context.user_data.get(
        "quiz_mode",
        QUIZ_MODE_KK_RU
    )

    progress = get_word_correct_count(
        context,
        question
    )

    # Сохраняем текущий вопрос

    context.user_data[
        "current_question"
    ] = {

        "kazakh":
            question["kazakh"],

        "russian":
            question["russian"],

        "correct":
            correct_answer,

        "answers":
            answers,

        "mode":
            mode,
    }

    buttons = []

    for index, answer_text in enumerate(
        answers
    ):

        buttons.append([

            InlineKeyboardButton(
                answer_text,
                callback_data=(
                    f"answer:{index}"
                )
            )

        ])

    keyboard = InlineKeyboardMarkup(
        buttons
    )

    # Заголовок режима

    if mode == QUIZ_MODE_ERRORS:

        title = (
            "📚 <b>Тренировка ошибок</b>"
        )

    elif mode == QUIZ_MODE_RU_KK:

        title = (
            "🇷🇺 → 🇰🇿 "
            "<b>Русский → Казахский</b>"
        )

    else:

        title = (
            "🇰🇿 → 🇷🇺 "
            "<b>Казахский → Русский</b>"
        )

    await context.bot.send_message(

        chat_id=chat_id,

        text=(

            f"{title}\n\n"

            f"<b>{question_text}</b>\n\n"

            f"Прогресс слова: "
            f"<b>{progress}/"
            f"{WORDS_TO_LEARN}</b>\n\n"

            "Выберите перевод:"
        ),

        reply_markup=keyboard,

        parse_mode="HTML",
    )


# =========================================================
# /quiz
# =========================================================

async def quiz(
    update,
    context
):

    context.user_data[
        "quiz_mode"
    ] = QUIZ_MODE_KK_RU

    await send_question(
        update.effective_chat.id,
        context
    )


# =========================================================
# Меню выбора теста
# =========================================================

async def quiz_menu(
    update,
    context
):

    query = update.callback_query

    if query:

        await query.answer()

        await query.edit_message_text(

            "🎯 <b>Выбери режим теста:</b>",

            reply_markup=InlineKeyboardMarkup([

                [

                    InlineKeyboardButton(
                        "🇰🇿 → 🇷🇺 "
                        "Казахский → Русский",
                        callback_data=(
                            "quiz:kk_ru"
                        )
                    )

                ],

                [

                    InlineKeyboardButton(
                        "🇷🇺 → 🇰🇿 "
                        "Русский → Казахский",
                        callback_data=(
                            "quiz:ru_kk"
                        )
                    )

                ],

                [

                    InlineKeyboardButton(
                        "📚 Тренировать ошибки",
                        callback_data=(
                            "quiz:errors"
                        )
                    )

                ],

                [

                    InlineKeyboardButton(
                        "◀️ Назад",
                        callback_data=(
                            "start_menu"
                        )
                    )

                ]

            ]),

            parse_mode="HTML"
        )

    else:

        await update.message.reply_text(

            "🎯 <b>Выбери режим теста:</b>",

            reply_markup=InlineKeyboardMarkup([

                [

                    InlineKeyboardButton(
                        "🇰🇿 → 🇷🇺 "
                        "Казахский → Русский",
                        callback_data=(
                            "quiz:kk_ru"
                        )
                    )

                ],

                [

                    InlineKeyboardButton(
                        "🇷🇺 → 🇰🇿 "
                        "Русский → Казахский",
                        callback_data=(
                            "quiz:ru_kk"
                        )
                    )

                ],

                [

                    InlineKeyboardButton(
                        "📚 Тренировать ошибки",
                        callback_data=(
                            "quiz:errors"
                        )
                    )

                ]

            ]),

            parse_mode="HTML"
        )


# =========================================================
# Запуск выбранного режима
# =========================================================

async def start_quiz_mode(
    update,
    context,
    mode
):

    query = update.callback_query

    await query.answer()

    context.user_data[
        "quiz_mode"
    ] = mode

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


# =========================================================
# Обработка ответа
# =========================================================

async def answer(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    question = context.user_data.get(
        "current_question"
    )

    if not question:

        await query.edit_message_text(

            "Вопрос устарел.\n\n"
            "Нажмите /quiz, чтобы "
            "начать новый тест."
        )

        return

    try:

        answer_index = int(
            query.data.split(":")[1]
        )

        selected_answer = (
            question["answers"][
                answer_index
            ]
        )

    except (
        ValueError,
        IndexError
    ):

        await query.edit_message_text(

            "Эта кнопка больше "
            "недействительна.\n\n"
            "Запустите новый тест."
        )

        return

    correct_answer = question[
        "correct"
    ]

    stats = get_statistics(
        context
    )

    stats["total"] += 1

    # ВАЖНО:
    # word всегда содержит оба перевода

    word = {

        "kazakh":
            question["kazakh"],

        "russian":
            question["russian"],
    }

    # -----------------------------------------------------
    # Правильно
    # -----------------------------------------------------

    if selected_answer == correct_answer:

        stats["correct"] += 1

        increase_word_progress(
            context,
            word
        )

        remove_mistake(
            context,
            word
        )

        correct_count = (
            get_word_correct_count(
                context,
                word
            )
        )

        if correct_count >= WORDS_TO_LEARN:

            result = (

                "✅ <b>Правильно!</b>\n\n"
                f"Перевод: <b>{correct_answer}</b>\n"
                "🎓 <b>Слово выучено!</b>\n"

                f"Прогресс: "
                f"<b>{WORDS_TO_LEARN}/"
                f"{WORDS_TO_LEARN}</b>"
            )

        else:

            result = (

                "✅ <b>Правильно!</b>\n\n"
                f"Перевод: <b>{correct_answer}</b>\n"
                f"Прогресс слова: "
                f"<b>{correct_count}/"
                f"{WORDS_TO_LEARN}</b>"
            )

    # -----------------------------------------------------
    # Неправильно
    # -----------------------------------------------------

    else:

        stats["wrong"] += 1

        # Сбрасываем прогресс

        reset_word_progress(
            context,
            word
        )

        # Записываем ошибку

        add_mistake(
            context,
            word
        )

        mistakes = get_mistakes(
            context
        )

        error_count = mistakes[
            question["kazakh"]
        ]["wrong"]

        result = (

            "❌ <b>Неправильно.</b>\n\n"

            f"Правильный ответ: "
            f"<b>{correct_answer}</b>\n\n"

            "Прогресс слова сброшен: "
            "<b>0/5</b>\n"

            f"Ошибок по этому слову: "
            f"<b>{error_count}</b>"
        )

    # -----------------------------------------------------
    # Кнопки после ответа
    # -----------------------------------------------------

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
                callback_data=(
                    "dictionary:0"
                )
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


# =========================================================
# Следующий вопрос
# =========================================================

async def next_question(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    progress = get_word_progress(
        context
    )

    available_words = [

        word

        for word in WORDS

        if progress.get(
            word["kazakh"],
            0
        ) < WORDS_TO_LEARN

    ]

    # Если все слова изучены
    # и мы в обычном режиме

    if (

        not available_words

        and context.user_data.get(
            "quiz_mode",
            QUIZ_MODE_KK_RU
        ) != QUIZ_MODE_ERRORS

    ):

        await query.edit_message_text(

            "🎉 <b>Поздравляю!</b>\n\n"

            f"Ты изучил все "
            f"<b>{len(WORDS)}</b> слов!\n\n"

            "Теперь можно повторять слова "
            "или тренировать ошибки.",

            reply_markup=InlineKeyboardMarkup([

                [

                    InlineKeyboardButton(
                        "🔄 Повторить все",
                        callback_data=(
                            "repeat_all"
                        )
                    )

                ],

                [

                    InlineKeyboardButton(
                        "📚 Мои ошибки",
                        callback_data=(
                            "mistakes"
                        )
                    )

                ],

                [

                    InlineKeyboardButton(
                        "📖 Словарь",
                        callback_data=(
                            "dictionary:0"
                        )
                    )

                ]

            ]),

            parse_mode="HTML"
        )

        return

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


# =========================================================
# Повторить все
# =========================================================

async def repeat_all(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    context.user_data[
        "quiz_mode"
    ] = QUIZ_MODE_KK_RU

    # Полностью сбрасываем прогресс
    context.user_data[
        "word_progress"
    ] = {}

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


# =========================================================
# Статистика
# =========================================================

async def stats(
    update,
    context
):

    user_stats = get_statistics(
        context
    )

    total = user_stats[
        "total"
    ]

    correct = user_stats[
        "correct"
    ]

    wrong = user_stats[
        "wrong"
    ]

    percentage = (

        correct / total * 100

        if total

        else 0
    )

    learned = (
        get_learned_words_count(
            context
        )
    )

    in_progress = (
        get_words_in_progress_count(
            context
        )
    )

    not_started = max(

        0,

        len(WORDS)
        - learned
        - in_progress
    )

    mistakes = get_mistakes(
        context
    )

    learned_percentage = (

        learned / len(WORDS) * 100

        if WORDS

        else 0
    )

    text = (

        "📊 <b>Твоя статистика</b>\n\n"

        "📚 <b>Изучение слов</b>\n\n"

        f"🎓 Изучено: "
        f"<b>{learned}</b> / "
        f"{len(WORDS)} "
        f"({learned_percentage:.1f}%)\n"

        f"📖 В процессе: "
        f"<b>{in_progress}</b>\n"

        f"🆕 Не начинали: "
        f"<b>{not_started}</b>\n\n"

        "🎯 <b>Результаты тестов</b>\n\n"

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
                "🎯 Тест",
                callback_data="quiz_menu"
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
                callback_data=(
                    "dictionary:0"
                )
            )

        ]

    ])

    if update.callback_query:

        query = update.callback_query

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


# =========================================================
# Мои ошибки
# =========================================================

async def mistakes(
    update,
    context
):

    query = update.callback_query

    if query:

        await query.answer()

    mistakes_data = get_mistakes(
        context
    )

    if not mistakes_data:

        text = (

            "📚 <b>Мои ошибки</b>\n\n"

            "🎉 Пока ошибок нет!\n\n"

            "Продолжай проходить тест."
        )

        keyboard = InlineKeyboardMarkup([

            [

                InlineKeyboardButton(
                    "🎯 Тест",
                    callback_data="quiz_menu"
                )

            ],

            [

                InlineKeyboardButton(
                    "📖 Словарь",
                    callback_data=(
                        "dictionary:0"
                    )
                )

            ]

        ])

    else:

        words = sorted(

            mistakes_data.values(),

            key=lambda x: x["wrong"],

            reverse=True
        )

        text_lines = [

            "📚 <b>Мои ошибки</b>",

            "",

            f"Всего слов: "
            f"<b>{len(words)}</b>",

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

        text = "\n".join(
            text_lines
        )

        keyboard = InlineKeyboardMarkup([

            [

                InlineKeyboardButton(
                    "🎯 Тренировать ошибки",
                    callback_data=(
                        "quiz:errors"
                    )
                )

            ],

            [

                InlineKeyboardButton(
                    "📖 Словарь",
                    callback_data=(
                        "dictionary:0"
                    )
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


# =========================================================
# Словарь
# =========================================================

async def dictionary(
    update,
    context
):

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

    total_words = len(
        WORDS
    )

    total_pages = math.ceil(

        total_words
        / WORDS_PER_PAGE
    )

    if total_pages == 0:

        text = "📖 Словарь пуст."

        if message:

            await message.edit_text(
                text
            )

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

    start = (
        page
        * WORDS_PER_PAGE
    )

    end = min(

        start
        + WORDS_PER_PAGE,

        total_words
    )

    page_words = WORDS[
        start:end
    ]

    text_lines = [

        f"📖 <b>Словарь</b>  •  "
        f"страница "
        f"{page + 1}/"
        f"{total_pages}",

        ""
    ]

    progress = get_word_progress(
        context
    )

    for index, word in enumerate(

        page_words,

        start=start + 1

    ):

        word_progress = progress.get(

            word["kazakh"],

            0
        )

        if word_progress >= WORDS_TO_LEARN:

            status = "🎓"

        elif word_progress > 0:

            status = (
                f"🔄 {word_progress}/"
                f"{WORDS_TO_LEARN}"
            )

        else:

            status = "🆕"

        text_lines.append(

            f"<b>{index}.</b> "

            f"{status} "

            f"{word['kazakh']} — "
            f"{word['russian']}"
        )

    text = "\n".join(
        text_lines
    )

    buttons = []

    navigation = []

    if page > 0:

        navigation.append(

            InlineKeyboardButton(

                "⬅️ Предыдущие",

                callback_data=(
                    f"dictionary:"
                    f"{page - 1}"
                )
            )
        )

    if page < total_pages - 1:

        navigation.append(

            InlineKeyboardButton(

                "Следующие ➡️",

                callback_data=(
                    f"dictionary:"
                    f"{page + 1}"
                )
            )
        )

    if navigation:

        buttons.append(
            navigation
        )

    buttons.append([

        InlineKeyboardButton(
            "🎯 Тест",
            callback_data="quiz_menu"
        ),

        InlineKeyboardButton(
            "📚 Ошибки",
            callback_data="mistakes"
        )

    ])

    buttons.append([

        InlineKeyboardButton(
            "📊 Статистика",
            callback_data="stats"
        )

    ])

    keyboard = InlineKeyboardMarkup(
        buttons
    )

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


# =========================================================
# Главное меню
# =========================================================

async def start(
    update,
    context
):

    await show_start_menu(
        update,
        context
    )


async def show_start_menu(
    update,
    context
):

    keyboard = InlineKeyboardMarkup([

        [

            InlineKeyboardButton(
                "🎯 Тест",
                callback_data="quiz_menu"
            )

        ],

        [

            InlineKeyboardButton(
                "📖 Словарь",
                callback_data=(
                    "dictionary:0"
                )
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

    if update.callback_query:

        await update.callback_query.edit_message_text(

            "Привет! Я бот для изучения "
            "казахского языка.\n\n"
            "Выбери режим:",

            reply_markup=keyboard
        )

    else:

        await update.message.reply_text(

            "Привет! Я бот для изучения "
            "казахского языка.\n\n"
            "Выбери режим:",

            reply_markup=keyboard
        )


# =========================================================
# Обработчик кнопок
# =========================================================

async def button_handler(
    update,
    context
):

    query = update.callback_query

    data = query.data

    # Ответ на вопрос

    if data.startswith(
        "answer:"
    ):

        await answer(
            update,
            context
        )

    # Следующее слово

    elif data == "next":

        await next_question(
            update,
            context
        )

    # Меню теста

    elif data == "quiz_menu":

        await quiz_menu(
            update,
            context
        )

    # Казахский -> Русский

    elif data == "quiz:kk_ru":

        await start_quiz_mode(

            update,

            context,

            QUIZ_MODE_KK_RU
        )

    # Русский -> Казахский

    elif data == "quiz:ru_kk":

        await start_quiz_mode(

            update,

            context,

            QUIZ_MODE_RU_KK
        )

    # Тренировка ошибок

    elif data == "quiz:errors":

        await start_quiz_mode(

            update,

            context,

            QUIZ_MODE_ERRORS
        )

    # Повторить все

    elif data == "repeat_all":

        await repeat_all(
            update,
            context
        )

    # Статистика

    elif data == "stats":

        await stats(
            update,
            context
        )

    # Словарь

    elif data.startswith(
        "dictionary:"
    ):

        await dictionary(
            update,
            context
        )

    # Ошибки

    elif data == "mistakes":

        await mistakes(
            update,
            context
        )

    # Главное меню

    elif data == "start_menu":

        await show_start_menu(
            update,
            context
        )


# =========================================================
# Запуск
# =========================================================

def main():

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # /start

    application.add_handler(

        CommandHandler(
            "start",
            start
        )
    )

    # /quiz

    application.add_handler(

        CommandHandler(
            "quiz",
            quiz
        )
    )

    # /stats

    application.add_handler(

        CommandHandler(
            "stats",
            stats
        )
    )

    # /dictionary

    application.add_handler(

        CommandHandler(
            "dictionary",
            dictionary
        )
    )

    # Все inline-кнопки

    application.add_handler(

        CallbackQueryHandler(
            button_handler
        )
    )

    # Webhook для Render

    application.run_webhook(

        listen="0.0.0.0",

        port=PORT,

        webhook_url=(
            f"{PUBLIC_URL}/telegram"
        ),

        url_path="telegram",
    )


# =========================================================
# Main
# =========================================================

if __name__ == "__main__":

    main()
