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


# ============================================================
# НАСТРОЙКИ
# ============================================================

TOKEN = os.environ["TELEGRAM_TOKEN"]
ADMIN_ID = os.environ["TELEGRAM_ADMIN_ID"]

PORT = int(os.environ.get("PORT", "10000"))
PUBLIC_URL = os.environ["RENDER_EXTERNAL_URL"]

# Сколько правильных ответов подряд нужно для изучения слова
WORDS_TO_LEARN = 5

# Количество слов на странице словаря
WORDS_PER_PAGE = 15

# Режимы тестирования
QUIZ_MODE_KK_RU = "kk_ru"
QUIZ_MODE_RU_KK = "ru_kk"
QUIZ_MODE_ERRORS = "errors"

# ============================================================
# ЗАГРУЗКА СЛОВ
# ============================================================

def load_words(filename):
    """Read words from Markdown table."""

    words = []

    with open(filename, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            # Пропускаем разделитель Markdown-таблицы
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

            # Пропускаем заголовок
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


# ============================================================
# ПОЛЬЗОВАТЕЛИ
# ============================================================

# В памяти храним ID пользователей.
# После перезапуска Render этот список сбросится,
# поскольку БД мы не используем.
users = set()


def register_user(user_id):
    """Register unique user."""

    users.add(user_id)


# ============================================================
# СТАТИСТИКА
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
# ПРОГРЕСС ИЗУЧЕНИЯ СЛОВ
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

    current += 1

    if current > WORDS_TO_LEARN:
        current = WORDS_TO_LEARN

    progress[kazakh] = current

    return current


def reset_word_progress(context, kazakh):

    progress = get_word_progress(context)

    progress[kazakh] = 0


# ============================================================
# ОШИБКИ
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
# ПОИСК СЛОВ
# ============================================================

def get_word_by_kazakh(kazakh):

    for word in WORDS:

        if word["kazakh"] == kazakh:
            return word

    return None


# ============================================================
# ГЕНЕРАЦИЯ ОБЫЧНОГО ВОПРОСА
# ============================================================

def get_normal_question(context, mode):

    progress = get_word_progress(context)

    available_words = [
        word
        for word in WORDS
        if progress.get(word["kazakh"], 0) < WORDS_TO_LEARN
    ]

    if not available_words:
        return None

    question = random.choice(available_words)

    if mode == QUIZ_MODE_KK_RU:

        correct_answer = question["russian"]

        other_words = [
            word
            for word in WORDS
            if word["kazakh"] != question["kazakh"]
            and word["russian"] != correct_answer
        ]

        question_text = question["kazakh"]

        answer_key = "russian"

    else:

        correct_answer = question["kazakh"]

        other_words = [
            word
            for word in WORDS
            if word["kazakh"] != correct_answer
        ]

        question_text = question["russian"]

        answer_key = "kazakh"

    # Убираем дубликаты вариантов
    unique_answers = set()

    wrong_answers = []

    random.shuffle(other_words)

    for word in other_words:

        answer = word[answer_key]

        if answer == correct_answer:
            continue

        if answer in unique_answers:
            continue

        unique_answers.add(answer)
        wrong_answers.append(answer)

        if len(wrong_answers) >= 3:
            break

    answers = [
        correct_answer,
        *wrong_answers
    ]

    random.shuffle(answers)

    return {
        "word": question,
        "question_text": question_text,
        "correct": correct_answer,
        "answers": answers,
        "mode": mode,
    }


# ============================================================
# ВОПРОС ИЗ ТРЕНИРОВКИ ОШИБОК
# ============================================================

def get_error_question(context):

    mistakes = get_mistakes(context)

    if not mistakes:
        return None

    mistake_words = list(mistakes.values())

    # Чем больше ошибок по слову,
    # тем выше вероятность его появления.
    weighted_words = []

    for mistake in mistake_words:

        count = max(
            1,
            mistake.get("wrong", 1)
        )

        for _ in range(count):
            weighted_words.append(mistake)

    mistake = random.choice(weighted_words)

    question = {
        "kazakh": mistake["kazakh"],
        "russian": mistake["russian"],
    }

    # В тренировке ошибок используем
    # казахский -> русский
    correct_answer = question["russian"]

    other_words = [
        word
        for word in WORDS
        if word["kazakh"] != question["kazakh"]
        and word["russian"] != correct_answer
    ]

    random.shuffle(other_words)

    wrong_answers = []

    for word in other_words:

        answer = word["russian"]

        if answer == correct_answer:
            continue

        if answer in wrong_answers:
            continue

        wrong_answers.append(answer)

        if len(wrong_answers) >= 3:
            break

    answers = [
        correct_answer,
        *wrong_answers
    ]

    random.shuffle(answers)

    return {
        "word": question,
        "question_text": question["kazakh"],
        "correct": correct_answer,
        "answers": answers,
        "mode": QUIZ_MODE_ERRORS,
    }


# ============================================================
# ПОЛУЧЕНИЕ СЛЕДУЮЩЕГО ВОПРОСА
# ============================================================

def get_question(context, mode):

    if mode == QUIZ_MODE_ERRORS:
        return get_error_question(context)

    return get_normal_question(
        context,
        mode
    )


# ============================================================
# НАЗВАНИЕ РЕЖИМА
# ============================================================

def get_mode_title(mode):

    if mode == QUIZ_MODE_RU_KK:
        return "🇷🇺 → 🇰🇿"

    if mode == QUIZ_MODE_ERRORS:
        return "📚 Тренировка ошибок"

    return "🇰🇿 → 🇷🇺"


# ============================================================
# ОТПРАВКА ВОПРОСА
# ============================================================

async def send_question(
    chat_id,
    context
):

    mode = context.user_data.get(
        "quiz_mode",
        QUIZ_MODE_KK_RU
    )

    question = get_question(
        context,
        mode
    )

    # Все слова выучены
    if question is None:

        if mode == QUIZ_MODE_ERRORS:

            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    "📚 <b>Тренировка ошибок</b>\n\n"
                    "🎉 Сейчас нет слов с ошибками!"
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            "🎯 К тесту",
                            callback_data="quiz_menu"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "📖 Словарь",
                            callback_data="dictionary:0"
                        )
                    ],
                ])
            )

            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🎉 <b>Все слова выучены!</b>\n\n"
                "Можно повторить их ещё раз "
                "или потренировать ошибки."
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔄 Повторить все",
                        callback_data="repeat_all"
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
                        "📖 Словарь",
                        callback_data="dictionary:0"
                    )
                ],
            ])
        )

        return

    # Сохраняем текущий вопрос
    context.user_data["current_question"] = question

    mode_title = get_mode_title(mode)

    word = question["word"]

    progress = get_word_progress_value(
        context,
        word["kazakh"]
    )

    if mode == QUIZ_MODE_ERRORS:

        progress_text = (
            f"Ошибок: "
            f"<b>{get_mistakes(context)[word['kazakh']]['wrong']}</b>"
        )

    else:

        progress_text = (
            f"Прогресс: "
            f"<b>{progress}/{WORDS_TO_LEARN}</b>"
        )

    buttons = []

    for index, answer_text in enumerate(
        question["answers"]
    ):

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
            f"<b>{mode_title}</b>\n\n"
            f"❓ <b>{question['question_text']}</b>\n\n"
            f"{progress_text}\n\n"
            "Выберите перевод:"
        ),
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ============================================================
# МЕНЮ ТЕСТИРОВАНИЯ
# ============================================================

async def show_quiz_menu(
    update,
    context,
    edit_message=False
):

    register_user(
        update.effective_user.id
    )

    text = (
        "🎯 <b>Тест</b>\n\n"
        "Выбери направление:"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🇰🇿 → 🇷🇺",
                callback_data="quiz_kk_ru"
            )
        ],
        [
            InlineKeyboardButton(
                "🇷🇺 → 🇰🇿",
                callback_data="quiz_ru_kk"
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
                "◀️ Назад",
                callback_data="start_menu"
            )
        ],
    ])

    if edit_message:

        await update.callback_query.edit_message_text(
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


async def quiz_command(
    update,
    context
):

    register_user(
        update.effective_user.id
    )

    await show_quiz_menu(
        update,
        context
    )


# ============================================================
# НАЧАЛО ТЕСТА
# ============================================================

async def start_quiz(
    update,
    context,
    mode
):

    register_user(
        update.effective_user.id
    )

    context.user_data["quiz_mode"] = mode

    query = update.callback_query

    await query.answer()

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


# ============================================================
# ОБРАБОТКА ОТВЕТА
# ============================================================

async def answer(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    register_user(
        update.effective_user.id
    )

    question = context.user_data.get(
        "current_question"
    )

    if not question:

        await query.edit_message_text(
            "Вопрос устарел. Нажмите /quiz, "
            "чтобы начать новый тест."
        )

        return

    try:

        answer_index = int(
            query.data.split(":")[1]
        )

        selected_answer = question["answers"][
            answer_index
        ]

    except (
        ValueError,
        IndexError,
        KeyError
    ):

        await query.edit_message_text(
            "Ошибка. Нажмите /quiz, "
            "чтобы начать новый тест."
        )

        return

    correct_answer = question["correct"]

    word = question["word"]

    mode = question["mode"]

    stats = get_statistics(context)

    stats["total"] += 1

    # ========================================================
    # ПРАВИЛЬНО
    # ========================================================

    if selected_answer == correct_answer:

        stats["correct"] += 1

        # В тренировке ошибок
        if mode == QUIZ_MODE_ERRORS:

            remove_mistake(
                context,
                word["kazakh"]
            )

            mistake = get_mistakes(
                context
            )

            remaining_errors = mistake.get(
                word["kazakh"],
                {}
            ).get(
                "wrong",
                0
            )

            if remaining_errors > 0:

                result = (
                    "✅ <b>Правильно!</b>\n\n"
                    f"Перевод: <b>{correct_answer}</b>\n\n"
                    f"Осталось ошибок: "
                    f"<b>{remaining_errors}</b>"
                )

            else:

                result = (
                    "✅ <b>Правильно!</b>\n\n"
                    f"Перевод: <b>{correct_answer}</b>\n\n"
                    "🎉 Ошибка по этому слову исправлена!"
                )

        else:

            progress = increase_word_progress(
                context,
                word["kazakh"]
            )

            # Если слово было в ошибках,
            # постепенно убираем его оттуда
            remove_mistake(
                context,
                word["kazakh"]
            )

            if progress >= WORDS_TO_LEARN:

                result = (
                    "✅ <b>Правильно!</b>\n\n"
                    f"Перевод: <b>{correct_answer}</b>\n\n"
                    "🎉 <b>Слово выучено!</b>"
                )

            else:

                result = (
                    "✅ <b>Правильно!</b>\n\n"
                    f"Перевод: <b>{correct_answer}</b>\n\n"
                    f"Прогресс: "
                    f"<b>{progress}/{WORDS_TO_LEARN}</b>"
                )

    # ========================================================
    # НЕПРАВИЛЬНО
    # ========================================================

    else:

        stats["wrong"] += 1

        # Ошибка сбрасывает прогресс
        reset_word_progress(
            context,
            word["kazakh"]
        )

        # Добавляем слово в тренировку ошибок
        add_mistake(
            context,
            word
        )

        mistakes = get_mistakes(
            context
        )

        wrong_count = mistakes[
            word["kazakh"]
        ]["wrong"]

        result = (
            "❌ <b>Неправильно.</b>\n\n"
            f"Правильный ответ: "
            f"<b>{correct_answer}</b>\n\n"
            f"📚 Ошибок по этому слову: "
            f"<b>{wrong_count}</b>"
        )

    # ========================================================
    # КНОПКИ ПОСЛЕ ОТВЕТА
    # ========================================================

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "➡️ Следующее слово",
                callback_data="next"
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
        f"❓ <b>{question['question_text']}</b>\n\n"
        f"{result}",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


# ============================================================
# СЛЕДУЮЩИЙ ВОПРОС
# ============================================================

async def next_question(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    register_user(
        update.effective_user.id
    )

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


# ============================================================
# ПОВТОРИТЬ ВСЕ СЛОВА
# ============================================================

async def repeat_all(
    update,
    context
):

    query = update.callback_query

    await query.answer()

    register_user(
        update.effective_user.id
    )

    # Сбрасываем прогресс
    context.user_data["word_progress"] = {}

    # Сбрасываем ошибки
    context.user_data["mistakes"] = {}

    # Русский -> казахский
    context.user_data["quiz_mode"] = (
        QUIZ_MODE_KK_RU
    )

    await query.message.delete()

    await send_question(
        query.message.chat_id,
        context
    )


# ============================================================
# СПИСОК ОШИБОК
# ============================================================

async def show_mistakes(
    update,
    context
):

    register_user(
        update.effective_user.id
    )

    mistakes = get_mistakes(context)

    if not mistakes:

        text = (
            "📚 <b>Мои ошибки</b>\n\n"
            "🎉 Ошибок пока нет!"
        )

    else:

        sorted_mistakes = sorted(
            mistakes.values(),
            key=lambda x: x["wrong"],
            reverse=True
        )

        lines = [
            "📚 <b>Мои ошибки</b>",
            ""
        ]

        for index, mistake in enumerate(
            sorted_mistakes,
            start=1
        ):

            lines.append(
                f"<b>{index}.</b> "
                f"{mistake['kazakh']} — "
                f"{mistake['russian']} "
                f"❌ {mistake['wrong']}"
            )

        text = "\n".join(lines)

    keyboard_buttons = []

    if mistakes:

        keyboard_buttons.append([
            InlineKeyboardButton(
                "🎯 Тренировать ошибки",
                callback_data="quiz_errors"
            )
        ])

    keyboard_buttons.append([
        InlineKeyboardButton(
            "🎯 К тесту",
            callback_data="quiz_menu"
        )
    ])

    keyboard_buttons.append([
        InlineKeyboardButton(
            "◀️ Назад",
            callback_data="start_menu"
        )
    ])

    keyboard = InlineKeyboardMarkup(
        keyboard_buttons
    )

    query = update.callback_query

    if query:

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


# ============================================================
# СТАТИСТИКА
# ============================================================

async def show_statistics(
    update,
    context
):

    register_user(
        update.effective_user.id
    )

    stats = get_statistics(context)

    total = stats["total"]
    correct = stats["correct"]
    wrong = stats["wrong"]

    percentage = (
        correct / total * 100
        if total
        else 0
    )

    progress = get_word_progress(context)

    learned = sum(
        1
        for word in WORDS
        if progress.get(
            word["kazakh"],
            0
        ) >= WORDS_TO_LEARN
    )

    in_progress = sum(
        1
        for word in WORDS
        if 0 < progress.get(
            word["kazakh"],
            0
        ) < WORDS_TO_LEARN
    )

    not_started = (
        len(WORDS)
        - learned
        - in_progress
    )

    mistakes_count = len(
        get_mistakes(context)
    )

    text = (
        "📊 <b>Твоя статистика</b>\n\n"

        f"🎯 Всего вопросов: "
        f"<b>{total}</b>\n"

        f"✅ Правильных: "
        f"<b>{correct}</b>\n"

        f"❌ Неправильных: "
        f"<b>{wrong}</b>\n"

        f"📈 Результат: "
        f"<b>{percentage:.1f}%</b>\n\n"

        f"📚 Всего слов: "
        f"<b>{len(WORDS)}</b>\n"

        f"🎓 Выучено: "
        f"<b>{learned}</b>\n"

        f"🔄 В процессе: "
        f"<b>{in_progress}</b>\n"

        f"🆕 Не начато: "
        f"<b>{not_started}</b>\n"

        f"❗ Слов с ошибками: "
        f"<b>{mistakes_count}</b>"
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
                callback_data="dictionary:0"
            )
        ],
        [
            InlineKeyboardButton(
                "◀️ Назад",
                callback_data="start_menu"
            )
        ],
    ])

    query = update.callback_query

    if query:

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


# ============================================================
# СЛОВАРЬ
# ============================================================

async def dictionary(
    update,
    context
):

    register_user(
        update.effective_user.id
    )

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

    if total_words == 0:

        text = "📖 Словарь пуст."

        if message:
            await message.edit_text(text)
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text
            )

        return

    total_pages = math.ceil(
        total_words / WORDS_PER_PAGE
    )

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

    progress = get_word_progress(context)

    text_lines = [
        (
            f"📖 <b>Словарь</b>  •  "
            f"страница {page + 1}/{total_pages}"
        ),
        ""
    ]

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
            f"{word['kazakh']} — "
            f"{word['russian']} "
            f"{status}"
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
            "🎯 Тест",
            callback_data="quiz_menu"
        ),
        InlineKeyboardButton(
            "📚 Ошибки",
            callback_data="mistakes"
        ),
    ])

    buttons.append([
        InlineKeyboardButton(
            "◀️ Назад",
            callback_data="start_menu"
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


# ============================================================
# ГЛАВНОЕ МЕНЮ
# ============================================================

async def show_start_menu(
    update,
    context,
    edit_message=False
):

    register_user(
        update.effective_user.id
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
                "📚 Тренировка ошибок",
                callback_data="quiz_errors"
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

    text = (
        "Привет! Я бот для изучения "
        "казахского языка. 🇰🇿\n\n"
        "Выбери режим:"
    )

    if edit_message:

        await update.callback_query.edit_message_text(
            text,
            reply_markup=keyboard
        )

    else:

        await update.message.reply_text(
            text,
            reply_markup=keyboard
        )


async def start(
    update,
    context
):

    register_user(
        update.effective_user.id
    )

    await show_start_menu(
        update,
        context
    )


# ============================================================
# КОМАНДА /USERS
# ============================================================

async def users_count(
    update,
    context
):

    user_id = update.effective_user.id

    if user_id != ADMIN_ID:

        await update.message.reply_text(
            "⛔ Доступ запрещён."
        )

        return

    await update.message.reply_text(
        f"👥 <b>Пользователей:</b> "
        f"<b>{len(users)}</b>",
        parse_mode="HTML"
    )


# ============================================================
# ОБРАБОТЧИК КНОПОК
# ============================================================

async def button_handler(
    update,
    context
):

    query = update.callback_query

    register_user(
        update.effective_user.id
    )

    data = query.data

    # --------------------------------------------------------
    # Главное меню
    # --------------------------------------------------------

    if data == "start_menu":

        await query.answer()

        await show_start_menu(
            update,
            context,
            edit_message=True
        )

    # --------------------------------------------------------
    # Меню теста
    # --------------------------------------------------------

    elif data == "quiz_menu":

        await query.answer()

        await show_quiz_menu(
            update,
            context,
            edit_message=True
        )

    # --------------------------------------------------------
    # Казахстанский -> русский
    # --------------------------------------------------------

    elif data == "quiz_kk_ru":

        await start_quiz(
            update,
            context,
            QUIZ_MODE_KK_RU
        )

    # --------------------------------------------------------
    # Русский -> казахский
    # --------------------------------------------------------

    elif data == "quiz_ru_kk":

        await start_quiz(
            update,
            context,
            QUIZ_MODE_RU_KK
        )

    # --------------------------------------------------------
    # Тренировка ошибок
    # --------------------------------------------------------

    elif data == "quiz_errors":

        await start_quiz(
            update,
            context,
            QUIZ_MODE_ERRORS
        )

    # --------------------------------------------------------
    # Ответ
    # --------------------------------------------------------

    elif data.startswith("answer:"):

        await answer(
            update,
            context
        )

    # --------------------------------------------------------
    # Следующее слово
    # --------------------------------------------------------

    elif data == "next":

        await next_question(
            update,
            context
        )

    # --------------------------------------------------------
    # Повторить все
    # --------------------------------------------------------

    elif data == "repeat_all":

        await repeat_all(
            update,
            context
        )

    # --------------------------------------------------------
    # Статистика
    # --------------------------------------------------------

    elif data == "stats":

        await show_statistics(
            update,
            context
        )

    # --------------------------------------------------------
    # Ошибки
    # --------------------------------------------------------

    elif data == "mistakes":

        await show_mistakes(
            update,
            context
        )

    # --------------------------------------------------------
    # Словарь
    # --------------------------------------------------------

    elif data.startswith("dictionary:"):

        await dictionary(
            update,
            context
        )


# ============================================================
# MAIN
# ============================================================

def main():

    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    # Команды

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
            show_statistics
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
            users_count
        )
    )

    # Кнопки

    application.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    # Webhook для Render

    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=f"{PUBLIC_URL}/telegram",
        url_path="telegram",
    )


# ============================================================
# START APPLICATION
# ============================================================

if __name__ == "__main__":
    main()
