import os
import asyncio
import sqlite3
import json
import logging
from groq import AsyncGroq  # Используем асинхронный клиент
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
# Инициализируем асинхронный клиент
client = AsyncGroq(api_key=GROQ_KEY) 
MODEL_NAME = "llama-3.3-70b-versatile"

# ... (db_query и init_db оставляем без изменений) ...
def db_query(sql, params=(), fetchone=False, commit=False):
    with sqlite3.connect("simulator.db") as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        if commit: conn.commit()
        return cursor.fetchone() if fetchone else cursor.fetchall()

def init_db():
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

# ... (Клавиатуры оставляем как есть) ...
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

# === ЛОГИКА ИИ (ТЕПЕРЬ ASYNC) ===
async def generate_profile():
    try:
        # Добавляем await
        res = await client.chat.completions.create(
            model="llama-3.1-8b-instant", # Для анкет можно модель подешевле/побыстрее
            messages=[{"role": "user", "content": "Придумай имя, возраст (15-45) и описание о себе. Одной короткой строкой на русском."}],
        )
        return res.choices[0].message.content
    except Exception as e:
        logging.error(f"Error in generate_profile: {e}")
        return "Мария, 21 год. Люблю музыку."

# === ОБРАБОТЧИКИ ===

@dp.message(F.text == "🔍 Найти собеседницу")
async def search_handler(message: types.Message):
    profile = await generate_profile() # Добавляем await
    db_query("INSERT OR REPLACE INTO temp_profiles (user_id, profile) VALUES (?, ?)", 
             (message.from_user.id, profile), commit=True)
    await message.answer(f"👤 **Анкета:**\n\n{profile}", reply_markup=get_action_inline())

# ... (start_chat и list_chats оставляем, они работают с БД нормально) ...

@dp.callback_query(F.data == "next_profile")
async def next_profile(callback: types.CallbackQuery):
    try:
        await callback.message.delete()
    except: pass # На случай если сообщение уже удалено
    
    profile = await generate_profile() # Добавляем await
    db_query("INSERT OR REPLACE INTO temp_profiles (user_id, profile) VALUES (?, ?)", 
             (callback.from_user.id, profile), commit=True)
    await callback.message.answer(f"👤 **Анкета:**\n\n{profile}", reply_markup=get_action_inline())
    await callback.answer()

@dp.message(F.text == "❌ Выйти из чата")
async def stop_chat(message: types.Message):
    db_query("UPDATE girls SET is_active = 0 WHERE user_id = ?", (message.from_user.id,), commit=True)
    await message.answer("Чат сохранен. Возвращаемся в меню.", reply_markup=get_main_kb())

# === ГЛАВНЫЙ ОБРАБОТЧИК (ОПТИМИЗИРОВАН) ===
@dp.message()
async def chat_handler(message: types.Message):
    uid = message.from_user.id
    active_chat = db_query("SELECT id, context, affinity, name_info FROM girls WHERE user_id = ? AND is_active = 1", (uid,), fetchone=True)
    
    if not active_chat:
        if message.text in ["🔍 Найти собеседницу", "🗂 Мои чаты"]: return # Игнорим кнопки меню тут
        return await message.answer("У вас нет активного чата.")

    chat_id, context_raw, affinity, profile = active_chat
    context = json.loads(context_raw)
    
    try:
        await bot.send_chat_action(message.chat.id, "typing")

        # ЭТАП 1: Оценка Affinity (Async)
        rank_res = await client.chat.completions.create(
            model="llama-3.1-8b-instant", 
            messages=[{"role": "system", "content": "Оцени сообщение. Если приятное/вежливое: +2. Грубое/скучное: -2. Нейтральное: 0. Верни ТОЛЬКО ЧИСЛО."},
                      {"role": "user", "content": message.text}]
        )
        try:
            val = rank_res.choices[0].message.content.strip()
            # Очистка на случай, если ИИ прислал лишний текст
            delta = int(''.join(filter(lambda x: x in '-0123456789', val)))
            new_affinity = max(0, min(100, affinity + delta))
        except:
            new_affinity = affinity

        # ЭТАП 2: Генерация ответа (Async)
        system_prompt = get_persona_prompt(profile, new_affinity)
        
        # Обновляем системный промпт
        if context and context[0]["role"] == "system":
            context[0]["content"] = system_prompt
        else:
            context.insert(0, {"role": "system", "content": system_prompt})

        context.append({"role": "user", "content": message.text})
        
        # ОГРАНИЧЕНИЕ КОНТЕКСТА: оставляем последние 10 сообщений + системный промпт
        if len(context) > 11:
            context = [context[0]] + context[-10:]

        res = await client.chat.completions.create(model=MODEL_NAME, messages=context)
        ans = res.choices[0].message.content
        context.append({"role": "assistant", "content": ans})
        
        db_query("UPDATE girls SET context = ?, affinity = ? WHERE id = ?", 
                 (json.dumps(context), new_affinity, chat_id), commit=True)
        
        await message.answer(ans)

    except Exception as e:
        logging.error(f"Ошибка в chat_handler: {e}")
        await message.answer("Что-то связь барахлит... Повтори?")

def get_persona_prompt(profile, affinity):
    base = f"Ты — {profile}. Твой текущий уровень близости с пользователем: {affinity}/100."
    if affinity < 15:
        mood = "Ты холодна, отвечаешь сухо и только по делу."
    elif affinity < 40:
        mood = "Ты дружелюбна, начинаешь доверять."
    elif affinity < 70:
        mood = "Ты проявляешь симпатию, флиртуешь."
    else:
        mood = "Ты глубоко влюблена, очень откровенна и ласкова."
    return f"{base} {mood} Пиши кратко, как в мессенджере."

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
