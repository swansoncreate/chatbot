import os
import asyncio
import sqlite3
import json
import logging
from groq import Groq
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)
MODEL_NAME = "llama-3.3-70b-versatile"

def db_query(sql, params=(), fetchone=False, commit=False):
    with sqlite3.connect("simulator.db") as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        if commit: conn.commit()
        return cursor.fetchone() if fetchone else cursor.fetchall()

def init_db():
    # Создаем таблицу сразу со всеми нужными полями
    db_query('''CREATE TABLE IF NOT EXISTS girls 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 user_id INTEGER, 
                 name_info TEXT, 
                 context TEXT, 
                 is_active INTEGER DEFAULT 0,
                 affinity INTEGER DEFAULT 0)''', commit=True)
    
    db_query('''CREATE TABLE IF NOT EXISTS temp_profiles 
                (user_id INTEGER PRIMARY KEY, profile TEXT)''', commit=True)

init_db()

# === КЛАВИАТУРЫ ===
def get_main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти собеседницу")],
        [KeyboardButton(text="🗂 Мои чаты")]
    ], resize_keyboard=True)

def get_chat_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="❌ Выйти из чата")]
    ], resize_keyboard=True)

def get_action_inline():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💌 Написать ей", callback_data="start_chat"),
         InlineKeyboardButton(text="⏭ Следующая", callback_data="next_profile")]
    ])

# === ЛОГИКА ИИ ===
def generate_profile():
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME, 
            messages=[{"role": "user", "content": "Придумай имя, возраст (15-45) и описание о себе. Одной короткой строкой на русском."}],
        )
        return res.choices[0].message.content
    except:
        return "Мария, 21 год. Люблю музыку."

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    # Добавляем аргумент reply_markup
    await message.answer("Добро пожаловать в симулятор знакомств!", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Найти собеседницу")
async def search_handler(message: types.Message):
    profile = generate_profile()
    db_query("INSERT OR REPLACE INTO temp_profiles (user_id, profile) VALUES (?, ?)", 
             (message.from_user.id, profile), commit=True)
    await message.answer(f"👤 **Анкета:**\n\n{profile}", reply_markup=get_action_inline())

@dp.callback_query(F.data == "start_chat")
async def start_chat(callback: types.CallbackQuery):
    uid = callback.from_user.id
    row = db_query("SELECT profile FROM temp_profiles WHERE user_id = ?", (uid,), fetchone=True)
    profile = row[0] if row else "Мария, 21 год"
    
    # Деактивируем текущие чаты и создаем новый
    db_query("UPDATE girls SET is_active = 0 WHERE user_id = ?", (uid,), commit=True)
    initial_ctx = json.dumps([{"role": "system", "content": f"Ты — {profile}. Пиши кратко, как в мессенджере."}])
    db_query("INSERT INTO girls (user_id, name_info, context, is_active) VALUES (?, ?, ?, 1)", 
             (uid, profile, initial_ctx), commit=True)
    
    await callback.message.answer(f"Вы начали чат с {profile.split(',')[0]}! Напишите ей что-нибудь.", reply_markup=get_chat_kb())
    await callback.answer()

@dp.callback_query(F.data == "next_profile")
async def next_profile(callback: types.CallbackQuery):
    # 1. Удаляем сообщение с текущей анкетой, чтобы не захламлять чат
    await callback.message.delete()
    
    # 2. Генерируем новый профиль и сохраняем во временную таблицу БД
    profile = generate_profile()
    db_query("INSERT OR REPLACE INTO temp_profiles (user_id, profile) VALUES (?, ?)", 
             (callback.from_user.id, profile), commit=True)

    # 3. Отправляем новое сообщение с новой анкетой и кнопками "Написать" / "Следующая"
    await callback.message.answer(f"👤 **Анкета:**\n\n{profile}", reply_markup=get_action_inline())
    
    # 4. Закрываем индикатор загрузки на кнопке
    await callback.answer()

@dp.message(F.text == "🗂 Мои чаты")
async def list_chats(message: types.Message):
    chats = db_query("SELECT id, name_info FROM girls WHERE user_id = ?", (message.from_user.id,))
    if not chats:
        return await message.answer("Список чатов пуст.")
    
    buttons = [[InlineKeyboardButton(text=f"💬 {c[1]}", callback_data=f"switch_{c[0]}")] for c in chats]
    await message.answer("Ваши переписки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("switch_"))
async def switch_chat(callback: types.CallbackQuery):
    chat_id = int(callback.data.split("_")[1])
    uid = callback.from_user.id
    db_query("UPDATE girls SET is_active = 0 WHERE user_id = ?", (uid,), commit=True)
    db_query("UPDATE girls SET is_active = 1 WHERE id = ?", (chat_id,), commit=True)
    await callback.message.answer("Чат переключен. Можете продолжать общение.", reply_markup=get_chat_kb())
    await callback.answer()

@dp.message(F.text == "❌ Выйти из чата")
async def stop_chat(message: types.Message):
    db_query("UPDATE girls SET is_active = 0 WHERE user_id = ?", (message.from_user.id,), commit=True)
    await message.answer("Чат сохранен. Возвращаемся в меню.", reply_markup=get_main_kb())

@dp.message()
async def chat_handler(message: types.Message):
    uid = message.from_user.id
    active_chat = db_query("SELECT id, context, affinity, name_info FROM girls WHERE user_id = ? AND is_active = 1", (uid,), fetchone=True)
    
    if not active_chat:
        return await message.answer("У вас нет активного чата.")

    chat_id, context_raw, affinity, profile = active_chat
    context = json.loads(context_raw)
    
    try:
        await bot.send_chat_action(message.chat.id, "typing")

        # ЭТАП 1: Оценка влияния сообщения на affinity
        # Создаем быстрый запрос для анализа (не добавляем его в историю)
        rank_res = client.chat.completions.create(
            model="llama-3.1-8b-instant", # Используем модель поменьше/побыстрее для оценки
            messages=[{"role": "system", "content": "Оцени сообщение пользователя. Если оно приятное, интересное или вежливое, верни '+2'. Если грубое или скучное, верни '-2'. Если нейтральное, верни '0'. Верни ТОЛЬКО ЧИСЛО."},
                      {"role": "user", "content": message.text}]
        )
        try:
            delta = int(rank_res.choices[0].message.content.strip())
            new_affinity = max(0, min(100, affinity + delta)) # Ограничиваем от 0 до 100
        except:
            new_affinity = affinity

        # ЭТАП 2: Генерация ответа с учетом новой близости
        system_prompt = get_persona_prompt(profile, new_affinity)
        
        # Обновляем системное сообщение в начале контекста
        if context and context[0]["role"] == "system":
            context[0]["content"] = system_prompt
        else:
            context.insert(0, {"role": "system", "content": system_prompt})

        context.append({"role": "user", "content": message.text})
        
        res = client.chat.completions.create(model=MODEL_NAME, messages=context)
        ans = res.choices[0].message.content
        context.append({"role": "assistant", "content": ans})
        
        # Сохраняем всё в базу
        db_query("UPDATE girls SET context = ?, affinity = ? WHERE id = ?", 
                 (json.dumps(context), new_affinity, chat_id), commit=True)
        
        await message.answer(ans)
        
        # (Опционально) Показываем юзеру, что лед тронулся
        if new_affinity != affinity:
            # Можно добавить индикатор в конце сообщения, если нужно
            # await message.answer(f"📈 Отношения: {new_affinity}/100")
            pass

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer("Что-то связь барахлит... Повтори?")

def get_persona_prompt(profile, affinity):
    base = f"Ты — {profile}. Твой текущий уровень близости с пользователем: {affinity}/100."
    
    if affinity < 15:
        mood = "Ты холодна, отвечаешь сухо и только по делу. Ты почти не доверяешь собеседнику."
    elif affinity < 40:
        mood = "Ты дружелюбна, начинаешь доверять, можешь немного пошутить."
    elif affinity < 70:
        mood = "Ты проявляешь симпатию, флиртуешь, задаешь личные вопросы и делишься своими мыслями."
    else:
        mood = "Ты глубоко привязана или влюблена. Ты очень откровенна, ласкова и доверяешь любые секреты."
        
    return f"{base} {mood} Пиши кратко, в стиле мессенджера, без лишнего официоза."

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
