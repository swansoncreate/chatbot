import asyncio
import random
import sqlite3
import json
import os
import urllib.parse
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

APPEARANCES = ["scandinavian blonde woman", "latin brunette woman", "asian cute girl", "slavic beautiful woman"]

async def generate_ai_personality():
    salt = random.randint(1, 9999)
    prompt = f"Create a unique female personality (ID {salt}). Return ONLY JSON: {{'name': 'Name', 'age': 20, 'hobby': 'Short description'}}"
    try:
        res = await groq_client.chat.completions.create(
            model="llama3-8b-8192", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=1.0
        )
        return json.loads(res.choices[0].message.content)
    except:
        return {"name": f"Мария {salt}", "age": 22, "hobby": "Музыка и кино"}

def get_chat_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Завершить", callback_data="exit_chat"),
         InlineKeyboardButton(text="🗑️ Удалить", callback_data="delete_chat")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти пару")],
        [KeyboardButton(text="📇 Контакты"), KeyboardButton(text="❤️ Статус")]
    ], resize_keyboard=True)
    await message.answer("Симулятор запущен!", reply_markup=kb)

@dp.message(F.text == "🔍 Найти пару")
async def search(message: types.Message):
    person = await generate_ai_personality()
    app = random.choice(APPEARANCES)
    seed = random.randint(1, 10**9)
    
    # БЕЗОПАСНОЕ ФОРМИРОВАНИЕ URL
    prompt_text = f"{app}, {person['hobby']}, high quality, realistic face"
    encoded_prompt = urllib.parse.quote(prompt_text)
    photo_url = f"https://image.pollinations.ai{encoded_prompt}?seed={seed}&width=512&height=512&nologo=true&model=flux"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Начать чат с {person['name']}", callback_data=f"set_{seed}")],
        [InlineKeyboardButton(text="👎 Дальше", callback_data="next")]
    ])
    
    global active_search_cache
    if 'active_search_cache' not in globals(): active_search_cache = {}
    active_search_cache[message.from_user.id] = {**person, "app": app, "seed": seed}
    
      try:
        await message.answer_photo(photo=photo_url, caption=f"✨ {person['name']}, {person['age']} лет\nХобби: {person['hobby']}", reply_markup=kb)
    except Exception as e:
        # Эта строка выведет ошибку в лог GitHub Actions
        print(f"ОШИБКА ОТПРАВКИ ФОТО: {e}") 
        await message.answer(f"✨ {person['name']}, {person['age']} лет\n(Фото временно недоступно)\nХобби: {person['hobby']}", reply_markup=kb)

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
    sys_prompt = f"Ты {data['name']}, тебе {data['age']}. Ты общаешься с парнем. Будь краткой и реалистичной."
    db_query("INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, 1, 15)", 
             (uid, data['name'], data['app'], data['seed'], sys_prompt, json.dumps([])))
    
    await c.message.answer(f"Чат с {data['name']} открыт!", reply_markup=get_chat_kb())
    await c.answer()

@dp.callback_query(F.data == "exit_chat")
async def exit_chat(c: types.CallbackQuery):
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (c.from_user.id,))
    await c.message.answer("Вы вышли в главное меню.")
    await c.answer()

@dp.callback_query(F.data == "delete_chat")
async def delete_chat(c: types.CallbackQuery):
    db_query("DELETE FROM chats WHERE user_id = ? AND is_active = 1", (c.from_user.id,))
    await c.message.answer("Чат удален.")
    await c.answer()

@dp.message(F.text == "❤️ Статус")
async def check_status(message: types.Message):
    res = db_query("SELECT girl_name, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (message.from_user.id,), fetchone=True)
    if res: await message.answer(f"Статус с {res[0]}: {res[1]}/100 ❤️")
    else: await message.answer("Нет активного чата.")

@dp.message(F.text == "📇 Контакты")
async def list_contacts(message: types.Message):
    girls = db_query("SELECT girl_name FROM chats WHERE user_id = ?", (message.from_user.id,), fetchall=True)
    if not girls: return await message.answer("Контактов нет.")
    btns = [[InlineKeyboardButton(text=f"💬 {n[0]}", callback_data=f"sw_{n[0]}")] for n in girls]
    await message.answer("Твои девушки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("sw_"))
async def switch_chat(c: types.CallbackQuery):
    name = c.data.split("_")[1]
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (c.from_user.id,))
    db_query("UPDATE chats SET is_active = 1 WHERE user_id = ? AND girl_name = ?", (c.from_user.id, name))
    await c.message.answer(f"Переключено на {name}.", reply_markup=get_chat_kb())
    await c.answer()

@dp.message()
async def talk(message: types.Message):
    uid = message.from_user.id
    res = db_query("SELECT girl_name, appearance, seed, system_prompt, history, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (uid,), fetchone=True)
    if not res: return

    name, app, seed, sys, hist_raw, trust = res
    history = json.loads(hist_raw)

    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile", 
            messages=[{"role":"system","content":sys}] + history[-6:] + [{"role":"user","content":message.text}]
        )
        answer = response.choices[0].message.content
        
        history.append({"role":"user","content":message.text})
        history.append({"role":"assistant","content":answer})
        db_query("UPDATE chats SET history = ? WHERE user_id = ? AND girl_name = ?", (json.dumps(history[-10:]), uid, name))
        
        await message.answer(answer, reply_markup=get_chat_kb())
    except:
        await message.answer("Извини, я отвлеклась. Повтори еще раз?")

async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
