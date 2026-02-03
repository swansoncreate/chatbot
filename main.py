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

APPEARANCES = ["scandinavian blonde", "latin brunette", "asian beauty", "slavic girl"]

async def generate_ai_personality():
    # Добавляем случайное число в промпт для разнообразия имен
    salt = random.randint(1, 9999)
    prompt = f"Придумай случайную уникальную личность (ID {salt}): Имя, Возраст (18-35), Хобби. Верни JSON: {{'name': '..', 'age': .., 'hobby': '..'}}"
    try:
        res = await groq_client.chat.completions.create(
            model="llama3-8b-8192", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=1.0 # Максимальный разброс имен
        )
        return json.loads(res.choices[0].message.content)
    except:
        return {"name": f"Девушка {salt}", "age": 21, "hobby": "путешествия"}

def get_chat_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Завершить чат", callback_data="exit_chat")],
        [InlineKeyboardButton(text="🗑️ Удалить диалог", callback_data="delete_chat")]
    ])

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
    app = random.choice(APPEARANCES)
    seed = random.randint(1, 10**9)
    
    # Исправленный URL фото
    photo_url = f"https://image.pollinations.ai{app.replace(' ', '_')}_model_face_age_{person['age']}?seed={seed}"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Начать чат с {person['name']}", callback_data=f"set_{seed}")],
        [InlineKeyboardButton(text="👎 Дальше", callback_data="next")]
    ])
    
    active_search_cache[message.from_user.id] = {**person, "app": app, "seed": seed}
    await message.answer_photo(photo=photo_url, caption=f"✨ {person['name']}, {person['age']} лет\nХобби: {person['hobby']}", reply_markup=kb)

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
    sys_prompt = f"Ты {data['name']}, тебе {data['age']}. Твое хобби: {data['hobby']}."
    db_query("INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, 1, 15)", 
             (uid, data['name'], data['app'], data['seed'], sys_prompt, json.dumps([])))
    
    await c.message.answer(f"Чат с {data['name']} открыт! Напиши ей что-нибудь.", reply_markup=get_chat_kb())
    await c.answer()

@dp.callback_query(F.data == "exit_chat")
async def exit_chat(c: types.CallbackQuery):
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (c.from_user.id,))
    await c.message.answer("Ты вышел из чата в главное меню.")
    await c.answer()

@dp.callback_query(F.data == "delete_chat")
async def delete_chat(c: types.CallbackQuery):
    db_query("DELETE FROM chats WHERE user_id = ? AND is_active = 1", (c.from_user.id,))
    await c.message.answer("Диалог полностью удален.")
    await c.answer()

@dp.message(F.text == "❤️ Статус")
async def check_status(message: types.Message):
    res = db_query("SELECT girl_name, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (message.from_user.id,), fetchone=True)
    if res: await message.answer(f"Статус с {res[0]}: {res[1]}/100 ❤️")
    else: await message.answer("Нет активного чата.")

@dp.message(F.text == "📇 Контакты")
async def list_contacts(message: types.Message):
    girls = db_query("SELECT DISTINCT girl_name FROM chats WHERE user_id = ?", (message.from_user.id,), fetchall=True)
    if not girls: return await message.answer("Список контактов пуст.")
    btns = [[InlineKeyboardButton(text=f"💬 {n[0]}", callback_data=f"sw_{n[0]}")] for n in girls]
    await message.answer("Твои знакомства:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("sw_"))
async def switch_chat(c: types.CallbackQuery):
    name = c.data.split("_")[1]
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (c.from_user.id,))
    db_query("UPDATE chats SET is_active = 1 WHERE user_id = ? AND girl_name = ?", (c.from_user.id, name))
    await c.message.answer(f"Теперь ты в чате с {name}.", reply_markup=get_chat_kb())
    await c.answer()

@dp.message()
async def talk(message: types.Message):
    uid = message.from_user.id
    res = db_query("SELECT girl_name, appearance, seed, system_prompt, history, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (uid,), fetchone=True)
    if not res: return

    name, app, seed, sys, hist_raw, trust = res
    history = json.loads(hist_raw)

    # Доверие
    try:
        ans = await groq_client.chat.completions.create(model="llama3-8b-8192", messages=[{"role":"user","content":f"User message: '{message.text}'. If friendly return +5, if rude -10. Return digit only."}])
        change = int(''.join(filter(lambda x: x in "-0123456789", ans.choices[0].message.content)))
    except: change = 1
    
    new_trust = max(0, min(100, trust + change))
    db_query("UPDATE chats SET trust_level = ? WHERE user_id = ? AND girl_name = ?", (new_trust, uid, name))

    mood = "сдержанная" if new_trust < 40 else "игривая" if new_trust < 80 else "влюбленная"
    prompt = f"{sys} Твой настрой: {mood}. Пиши как живая девушка, кратко."

    await bot.send_chat_action(message.chat.id, "typing")
    response = await groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile", 
        messages=[{"role":"system","content":prompt}] + history[-6:] + [{"role":"user","content":message.text}]
    )
    answer = response.choices[0].message.content

    history.append({"role":"user","content":message.text})
    history.append({"role":"assistant","content":answer})
    db_query("UPDATE chats SET history = ? WHERE user_id = ? AND girl_name = ?", (json.dumps(history[-10:]), uid, name))

    await message.answer(answer, reply_markup=get_chat_kb())

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
