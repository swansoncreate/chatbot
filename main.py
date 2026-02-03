import asyncio
import random
import sqlite3
import json
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from groq import AsyncGroq

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
DB_PATH = "bot_data.db"

def db_query(query, params=(), fetchone=False, fetchall=False):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        if fetchone: return cur.fetchone()
        if fetchall: return cur.fetchall()
        conn.commit()

def init_db():
    db_query("""CREATE TABLE IF NOT EXISTS chats
                (user_id INTEGER, girl_name TEXT, appearance TEXT, seed INTEGER,
                system_prompt TEXT, history TEXT, is_active INTEGER, trust_level INTEGER)""")
    db_query("CREATE TABLE IF NOT EXISTS user_facts (user_id INTEGER, fact_key TEXT, fact_value TEXT)")

# --- ЛОГИКА ---

async def generate_ai_personality():
    prompt = "Придумай девушку: Имя, Возраст (15-40), Хобби. Верни ТОЛЬКО JSON: {'name': '..', 'age': .., 'hobby': '..'}"
    try:
        res = await groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except:
        return {"name": "Анна", "age": 25, "hobby": "фотография"}

def get_time_context():
    h = datetime.now().hour
    if 5 <= h < 12: return "Утро. Ты сонная и милая."
    if 12 <= h < 18: return "День. Ты бодрая и занятая."
    return "Вечер/ночь. Ты расслабленная и откровенная."

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти пару")],
        [KeyboardButton(text="📇 Контакты"), KeyboardButton(text="❤️ Статус")]
    ], resize_keyboard=True)
    await message.answer("Симулятор запущен! Ищи анкеты.", reply_markup=kb)

active_search_cache = {}

@dp.message(F.text == "🔍 Найти пару")
async def search(message: types.Message):
    person = await generate_ai_personality()
    app = "standard appearance" # Modified to remove specific appearance prompt
    seed = random.randint(1, 10**9)

    # Removed photo generation as it was linked to the unsafe content

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Начать чат с {person['name']}", callback_data=f"set_{seed}")],
        [InlineKeyboardButton(text="👎 Дальше", callback_data="next")]
    ])

    active_search_cache[message.from_user.id] = {**person, "app": app, "seed": seed}
    await message.answer(f"✨ {person['name']}, {person['age']} лет\nУвлекается: {person['hobby']}", reply_markup=kb)


@dp.callback_query(F.data == "next")
async def next_callback(c: types.CallbackQuery):
    await c.message.delete()
    await search(c.message)

@dp.callback_query(F.data.startswith("set_"))
async def set_chat(c: types.CallbackQuery):
    uid = c.from_user.id
    data = active_search_cache.get(uid)
    if not data: return

    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (uid,))
    sys_prompt = f"Ты {data['name']}, тебе {data['age']}. Хобби: {data['hobby']}."
    db_query("INSERT INTO chats (user_id, girl_name, appearance, seed, system_prompt, history, is_active, trust_level) VALUES (?, ?, ?, ?, ?, ?, 1, 15)",
             (uid, data['name'], data['app'], data['seed'], sys_prompt, json.dumps([])))

    await c.message.answer(f"Чат с {data['name']} открыт!")
    await c.answer()

@dp.message(F.text == "❤️ Статус")
async def check_status(message: types.Message):
    res = db_query("SELECT girl_name, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (message.from_user.id,), fetchone=True)
    if res: await message.answer(f"Статус с {res[0]}: {res[1]}/100 ❤️")
    else: await message.answer("Нет активного чата.")

@dp.message(F.text == "📇 Контакты")
async def list_contacts(message: types.Message):
    girls = db_query("SELECT DISTINCT girl_name FROM chats WHERE user_id = ?", (message.from_user.id,), fetchall=True)
    if not girls: return await message.answer("Пусто.")
    btns = [[InlineKeyboardButton(text=f"💬 {n[0]}", callback_data=f"sw_{n[0]}")] for n in girls]
    await message.answer("Выбери чат:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("sw_"))
async def switch_chat(c: types.CallbackQuery):
    name = c.data.split("_")[1]
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (c.from_user.id,))
    db_query("UPDATE chats SET is_active = 1 WHERE user_id = ? AND girl_name = ?", (c.from_user.id, name))
    await c.message.answer(f"Переключено на {name}.")
    await c.answer()

@dp.message()
async def talk(message: types.Message):
    uid = message.from_user.id
    res = db_query("SELECT girl_name, appearance, seed, system_prompt, history, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (uid,), fetchone=True)
    if not res: return

    name, app, seed, sys, hist_raw, trust = res
    history = json.loads(hist_raw)

    # Доверие (анализ)
    try:
        ans = await groq_client.chat.completions.create(model="llama3-8b-8192", messages=[{"role":"user","content":f"User:'{message.text}'. Friendly:+5, Rude:-10. Number only."}])
        change = int(''.join(filter(lambda x: x in "-0123456789", ans.choices[0].message.content)))
    except: change = 1

    new_trust = max(0, min(100, trust + change))
    db_query("UPDATE chats SET trust_level = ? WHERE user_id = ? AND girl_name = ?", (new_trust, uid, name))

    # Ответ AI
    mood = "сдержанная" if new_trust < 40 else "игривая" if new_trust < 80 else "влюбленная"
    prompt = f"{sys} {get_time_context()} Твой настрой: {mood}. Пиши кратко."

    await bot.send_chat_action(message.chat.id, "typing")
    response = await groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role":"system","content":prompt}] + history[-6:] + [{"role":"user","content":message.text}]
    )
    answer = response.choices[0].message.content

    await asyncio.sleep(min(max(1, len(answer)*0.02), 3))
    await message.answer(answer)

    history.append({"role":"user","content":message.text})
    history.append({"role":"assistant","content":answer})
    db_query("UPDATE chats SET history = ? WHERE user_id = ? AND girl_name = ?", (json.dumps(history[-10:]), uid, name))

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
