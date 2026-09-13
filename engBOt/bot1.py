import asyncio
import logging
import sqlite3
from contextlib import contextmanager

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# --- КОНФІГУРАЦІЯ ---
# ⚠️ Вставте сюди ваш ДІЙСНИЙ токен з BotFather!
BOT_TOKEN = "8998891709:AAGcVvTwx_b5X74TQP6J4xCns3NrD7HtV_Q"

# Список Telegram ID усіх вчителів (підтримується декілька ID)
TEACHER_IDS = [1108561620, 5893932365]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DB_NAME = "school.db"

# --- 30 МОВ ---
LANGUAGES = {
    "uk": "🇺🇦 Українська", "en": "🇬🇧 English", "es": "🇪🇸 Español", "de": "🇩🇪 Deutsch",
    "pl": "🇵🇱 Polski", "fr": "🇫🇷 Français", "tr": "🇹🇷 Türkçe", "it": "🇮🇹 Italiano",
    "pt": "🇵🇹 Português", "ro": "🇷🇴 Română", "cs": "🇨🇿 Čeština", "hu": "🇭🇺 Magyar",
    "nl": "🇳🇱 Nederlands", "el": "🇬🇷 Ελληνικά", "sv": "🇸🇪 Svenska", "bg": "🇧🇬 Български",
    "da": "🇩🇰 Dansk", "fi": "🇫🇮 Suomi", "sk": "🇸🇰 Slovenčina", "hr": "🇭🇷 Hrvatski",
    "lt": "🇱🇹 Lietuvių", "lv": "🇱🇻 Latviešu", "et": "🇪🇪 Eesti", "zh": "🇨🇳 中文",
    "ja": "🇯🇵 日本語", "ko": "🇰🇷 한국어", "ar": "🇸🇦 العربية", "hi": "🇮🇳 हिन्दी",
    "ka": "🇬🇪 ქართული", "az": "🇦🇿 Azərbaycan"
}

# Словник текстів для інтерфейсу
TEXTS = {
    "btn_my_hw": {"uk": "📖 Мої ДЗ", "en": "📖 My Homework", "es": "📖 Mis deberes", "de": "📖 Meine Hausaufgaben", "pl": "📖 Moje zadania"},
    "btn_chat_teacher": {"uk": "💬 Чат з вчителем", "en": "💬 Chat with Teacher", "es": "💬 Chat con profesor", "de": "💬 Chat mit Lehrer", "pl": "💬 Czat z nauczycielem"},
    "btn_lang": {"uk": "🌐 Мова / Language", "en": "🌐 Language", "es": "🌐 Idioma", "de": "🌐 Sprache", "pl": "🌐 Język"},
    "welcome_teacher": {"uk": "👋 Вітаємо в панелі викладача!", "en": "👋 Welcome to the Teacher Panel!"},
    "welcome_student": {"uk": "👋 Привіт! Обери дію в меню нижче:", "en": "👋 Hello! Choose an option below:"},
    "not_in_list": {"uk": "❌ Вас немає у списку учнів. Зверніться до викладача.", "en": "❌ You are not in the student list."}
}

def get_text(key, lang_code="uk"):
    lang = lang_code if lang_code in TEXTS.get(key, {}) else "uk"
    return TEXTS.get(key, {}).get(lang, TEXTS.get(key, {}).get("uk", key))

# --- БАЗА ДАНИХ ---
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS students (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                lang TEXT DEFAULT 'uk'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS homeworks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_user_id INTEGER,
                text TEXT,
                file_id TEXT,
                file_type TEXT,
                deadline TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

init_db()

def get_user_lang(user_id):
    if user_id in TEACHER_IDS:
        return "uk"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT lang FROM students WHERE user_id = ?", (user_id,))
        res = cursor.fetchone()
        return res["lang"] if res and res["lang"] else "uk"

# --- СТАНИ FSM ---
class TeacherState(StatesGroup):
    add_student_name = State()
    add_student_id = State()
    hw_target = State()
    hw_content = State()
    hw_deadline = State()
    active_chat = State()

class StudentState(StatesGroup):
    active_chat = State()

# --- КЛАВІАТУРИ МЕНЮ (ПІД ТЕКСТОМ) ---
def get_teacher_reply_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📚 Надіслати ДЗ")
    builder.button(text="💬 Чати з учнями")
    builder.button(text="➕ Додати учня")
    builder.button(text="❌ Видалити учня")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)

def get_student_reply_kb(lang="uk"):
    builder = ReplyKeyboardBuilder()
    builder.button(text=get_text("btn_my_hw", lang))
    builder.button(text=get_text("btn_chat_teacher", lang))
    builder.button(text=get_text("btn_lang", lang))
    builder.adjust(2, 1)
    return builder.as_markup(resize_keyboard=True)

# --- СТАРТ (/start) ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if user_id in TEACHER_IDS:
        await message.answer(get_text("welcome_teacher"), reply_markup=get_teacher_reply_kb())
        return

    lang = get_user_lang(user_id)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM students WHERE user_id = ?", (user_id,))
        student = cursor.fetchone()

    if student:
        await message.answer(f"{get_text('welcome_student', lang)} ({student['name']})", reply_markup=get_student_reply_kb(lang))
    else:
        await message.answer(get_text("not_in_list", lang))

# ==========================================
#               ВИБІР МОВИ (30 МОВ)
# ==========================================
@dp.message(F.text.contains("Мова") | F.text.contains("Language") | F.text.contains("Idioma") | F.text.contains("Język"))
async def choose_language(message: types.Message):
    builder = InlineKeyboardBuilder()
    for code, name in LANGUAGES.items():
        builder.button(text=name, callback_data=f"set_lang_{code}")
    builder.adjust(2)
    await message.answer("Оберіть мову інтерфейсу / Select your language:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set_lang_"))
async def set_language(call: types.CallbackQuery):
    lang_code = call.data.split("_")[2]
    user_id = call.from_user.id

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE students SET lang = ? WHERE user_id = ?", (lang_code, user_id))
        conn.commit()

    lang_name = LANGUAGES.get(lang_code, "Українська")
    await call.message.edit_text(f"✅ Мову змінено на: {lang_name}")
    await call.message.answer("Меню оновлено:", reply_markup=get_student_reply_kb(lang_code))
    await call.answer()

# ==========================================
#               ОСОБИСТІ ЧАТИ
# ==========================================

# 1. Викладач обирає учня для чату
@dp.message(F.text == "💬 Чати з учнями")
async def teacher_chats_list(message: types.Message):
    if message.from_user.id not in TEACHER_IDS:
        return

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name FROM students")
        students = cursor.fetchall()

    if not students:
        await message.answer("Немає доданих учнів.")
        return

    builder = InlineKeyboardBuilder()
    for s in students:
        builder.button(text=f"💬 {s['name']}", callback_data=f"t_chat_with_{s['user_id']}")
    builder.adjust(1)

    await message.answer("Оберіть учня для листування:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("t_chat_with_"))
async def teacher_open_chat(call: types.CallbackQuery, state: FSMContext):
    student_id = int(call.data.split("_")[3])
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM students WHERE user_id = ?", (student_id,))
        student = cursor.fetchone()

    await state.update_data(chat_student_id=student_id)
    await state.set_state(TeacherState.active_chat)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Завершити чат", callback_data="close_chat")

    await call.message.answer(
        f"💬 Чат з учнем **{student['name']}** відкрито!\nУсе, що ви напишете сюди, надійде учневі.",
        parse_mode="Markdown",
        reply_markup=builder.as_markup()
    )
    await call.answer()

@dp.message(TeacherState.active_chat)
async def teacher_send_chat_msg(message: types.Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get("chat_student_id")

    try:
        await message.copy_to(chat_id=student_id)
        await message.answer("📩 Надіслано учню!")
    except Exception as e:
        await message.answer(f"❌ Не вдалося надіслати повідомлення: {e}")

# 2. Учень пише вчителю
@dp.message(F.text.contains("Чат з вчителем") | F.text.contains("Chat with Teacher"))
async def student_open_chat(message: types.Message, state: FSMContext):
    await state.set_state(StudentState.active_chat)

    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Завершити чат", callback_data="close_chat")

    await message.answer(
        "💬 Чат з вчителем відкрито!\nНапишіть ваше повідомлення, і вчитель його отримає.",
        reply_markup=builder.as_markup()
    )

@dp.message(StudentState.active_chat)
async def student_send_chat_msg(message: types.Message):
    user_id = message.from_user.id
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM students WHERE user_id = ?", (user_id,))
        student = cursor.fetchone()

    student_name = student["name"] if student else "Учень"

    # Надсилаємо усім викладачам
    for teacher_id in TEACHER_IDS:
        try:
            await bot.send_message(teacher_id, f"💬 **Повідомлення від {student_name}:**", parse_mode="Markdown")
            await message.copy_to(chat_id=teacher_id)
        except Exception:
            pass

    await message.answer("📩 Надіслано вчителю!")

@dp.callback_query(F.data == "close_chat")
async def close_chat(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("❌ Чат завершено.")
    await call.answer()

# ==========================================
#               УПРАВЛІННЯ УЧНЯМИ
# ==========================================
@dp.message(F.text == "➕ Додати учня")
async def t_add_student_start(message: types.Message, state: FSMContext):
    if message.from_user.id not in TEACHER_IDS:
        return
    await state.set_state(TeacherState.add_student_name)
    await message.answer("Введіть ім'я або ПІБ учня:")

@dp.message(TeacherState.add_student_name)
async def t_add_student_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(TeacherState.add_student_id)
    await message.answer("Тепер введіть Telegram ID учня (тільки цифри):")

@dp.message(TeacherState.add_student_id)
async def t_add_student_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ ID має складатися лише з цифр.")
        return

    data = await state.get_data()
    student_id = int(message.text)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO students (user_id, name) VALUES (?, ?)", (student_id, data["name"]))
        conn.commit()

    await state.clear()
    await message.answer(f"✅ Учня {data['name']} (ID: {student_id}) додано!", reply_markup=get_teacher_reply_kb())

@dp.message(F.text == "❌ Видалити учня")
async def t_del_student_start(message: types.Message):
    if message.from_user.id not in TEACHER_IDS:
        return
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name FROM students")
        students = cursor.fetchall()

    if not students:
        await message.answer("Список порожній.")
        return

    builder = InlineKeyboardBuilder()
    for s in students:
        builder.button(text=f"❌ {s['name']}", callback_data=f"del_stud_{s['user_id']}")
    builder.adjust(1)

    await message.answer("Оберіть учня для видалення:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("del_stud_"))
async def t_del_student_process(call: types.CallbackQuery):
    student_id = int(call.data.split("_")[2])
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM students WHERE user_id = ?", (student_id,))
        conn.commit()

    await call.message.edit_text("✅ Учня видалено!")
    await call.answer()

# ==========================================
#               ВІДПРАВКА ДЗ
# ==========================================
@dp.message(F.text == "📚 Надіслати ДЗ")
async def t_send_hw_choose_target(message: types.Message, state: FSMContext):
    if message.from_user.id not in TEACHER_IDS:
        return
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name FROM students")
        students = cursor.fetchall()

    if not students:
        await message.answer("❌ Немає доданих учнів!")
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="🌐 Усім учням", callback_data="hw_target_all")
    for s in students:
        builder.button(text=f"👤 {s['name']}", callback_data=f"hw_target_{s['user_id']}")

    builder.adjust(1)
    await message.answer("Оберіть адресата для ДЗ:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("hw_target_"))
async def t_send_hw_start_content(call: types.CallbackQuery, state: FSMContext):
    target = call.data.replace("hw_target_", "")
    target_id = None if target == "all" else int(target)

    await state.update_data(target_user_id=target_id)
    await state.set_state(TeacherState.hw_content)
    
    await call.message.answer("Надішліть вміст ДЗ (текст, фото, відео або документ):")
    await call.answer()

@dp.message(TeacherState.hw_content)
async def t_send_hw_content(message: types.Message, state: FSMContext):
    file_id = None
    file_type = None
    text = message.caption or message.text or ""

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"

    await state.update_data(text=text, file_id=file_id, file_type=file_type)
    await state.set_state(TeacherState.hw_deadline)
    await message.answer("Вкажіть дедлайн (наприклад: до завтра 18:00):")

@dp.message(TeacherState.hw_deadline)
async def t_send_hw_deadline(message: types.Message, state: FSMContext):
    data = await state.get_data()
    deadline = message.text.strip()
    target_user_id = data["target_user_id"]

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO homeworks (target_user_id, text, file_id, file_type, deadline) VALUES (?, ?, ?, ?, ?)",
            (target_user_id, data["text"], data["file_id"], data["file_type"], deadline)
        )
        conn.commit()
        
        if target_user_id is None:
            cursor.execute("SELECT user_id FROM students")
            recipients = [row["user_id"] for row in cursor.fetchall()]
        else:
            recipients = [target_user_id]

    content_text = data['text'] if data['text'] else "(Вкладений файл)"
    msg_caption = f"📚 Нове домашнє завдання!\n\n{content_text}\n\n⏳ Дедлайн: {deadline}"
    sent_count = 0

    for uid in recipients:
        try:
            if data["file_type"] == "photo":
                await bot.send_photo(uid, photo=data["file_id"], caption=msg_caption)
            elif data["file_type"] == "document":
                await bot.send_document(uid, document=data["file_id"], caption=msg_caption)
            elif data["file_type"] == "video":
                await bot.send_video(uid, video=data["file_id"], caption=msg_caption)
            else:
                await bot.send_message(uid, msg_caption)
            sent_count += 1
        except Exception:
            pass

    await state.clear()
    await message.answer(f"✅ ДЗ успішно збережено та відправлено ({sent_count} учн.)!", reply_markup=get_teacher_reply_kb())

# ==========================================
#               ПЕРЕГЛЯД ДЗ УЧНЕМ
# ==========================================
@dp.message(F.text.contains("Мої ДЗ") | F.text.contains("My Homework") | F.text.contains("Mis deberes"))
async def s_my_hw_list(message: types.Message):
    user_id = message.from_user.id
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, text, deadline, created_at 
            FROM homeworks 
            WHERE target_user_id IS NULL OR target_user_id = ? 
            ORDER BY id DESC
        """, (user_id,))
        hws = cursor.fetchall()

    if not hws:
        await message.answer("Активних домашніх завдань немає 🏝")
        return

    builder = InlineKeyboardBuilder()
    for hw in hws:
        date_str = hw["created_at"][:10]
        preview = (hw["text"][:20] + "...") if hw["text"] else "Файл/Медіа"
        builder.button(text=f"📚 {date_str} - {preview}", callback_data=f"view_hw_{hw['id']}")
    
    builder.adjust(1)
    await message.answer("📜 Ваші домашні завдання:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("view_hw_"))
async def s_view_hw(call: types.CallbackQuery):
    hw_id = int(call.data.split("_")[2])
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT text, file_id, file_type, deadline, created_at FROM homeworks WHERE id = ?", (hw_id,))
        hw = cursor.fetchone()

    if not hw:
        await call.message.answer("Завдання не знайдено.")
        await call.answer()
        return

    content_text = hw['text'] if hw['text'] else "(Файл без опису)"
    msg_caption = (
        f"📖 Домашнє завдання\n\n"
        f"📅 Опубліковано: {hw['created_at'][:16]}\n"
        f"⏳ Дедлайн: {hw['deadline']}\n\n"
        f"💬 {content_text}"
    )

    if hw["file_type"] == "photo":
        await call.message.answer_photo(hw["file_id"], caption=msg_caption)
    elif hw["file_type"] == "document":
        await call.message.answer_document(hw["file_id"], caption=msg_caption)
    elif hw["file_type"] == "video":
        await call.message.answer_video(hw["file_id"], caption=msg_caption)
    else:
        await call.message.answer(msg_caption)

    await call.answer()

# --- ЗАПУСК ---
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())