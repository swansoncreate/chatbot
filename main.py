import asyncio
import random
import sqlite3
import json
import os
import urllib.parse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
from groq import AsyncGroq

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
groq_client = AsyncGroq(api_key=GROQ_API_KEY)
DB_PATH = "bot_data.db"
active_search_cache = {}

# --- БД ---
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

# --- ВСПОМОГАТЕЛЬНОЕ ---
APPEARANCES = ["scandinavian blonde woman", "latin brunette woman", "asian cute girl", "slavic beautiful woman"]

def get_chat_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Выйти", callback_data="exit_chat"),
         InlineKeyboardButton(text="🗑 Удалить", callback_data="delete_chat")]
    ])
    
async def generate_ai_personality():
    salt = random.randint(1, 9999)
    # Просим JSON с русским описанием и английским промптом для фото
    prompt = ("Create a unique female personality. "
              "Return ONLY JSON: {'name': 'Имя', 'age': 22, 'hobby': 'Хобби на русском', "
              "'photo_style': 'detailed english prompt for image generation based on hobby'}")
    try:
        res = await groq_client.chat.completions.create(
            model="llama3-8b-8192", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices[0].message.content)
    except Exception as e:
        print(f"Ошибка Groq: {e}")
        return {"name": "Анна", "age": 21, "hobby": "Фотография", "photo_style": "girl with a camera"}

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти пару"), KeyboardButton(text="❤️ Статус")],
        [KeyboardButton(text="📇 Контакты")]
    ], resize_keyboard=True)
    await message.answer("Симулятор запущен!", reply_markup=kb)

@dp.message(F.text == "🔍 Найти пару")
async def search(message: types.Message):
    try:
        person = await generate_ai_personality()
        app = random.choice(APPEARANCES)
        seed = random.randint(1, 10**9)
        
        # Собираем промпт: внешность + стиль от ИИ (на английском)
        # Очищаем от кавычек на всякий случай
        clean_style = person.get('photo_style', 'beautiful face').replace("'", "").replace('"', "")
        full_prompt = f"{app}, {clean_style}, high quality, realistic face"
        
        encoded_prompt = urllib.parse.quote(full_prompt)
        
        # ЭТАЛОННАЯ ССЫЛКА
        photo_url = f"https://image.pollinations.ai{encoded_prompt}?seed={seed}&width=512&height=512&nologo=true"
        
        print(f"DEBUG URL: {photo_url}") # Проверка в GitHub Actions

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Начать общение", callback_data=f"set_{seed}")],
            [InlineKeyboardButton(text="⏭ Следующая", callback_data="next")]
        ])
        
        active_search_cache[message.from_user.id] = {**person, "app": app, "seed": seed}

        await message.answer_photo(
            photo=photo_url, 
            caption=f"✨ {person['name']}, {person['age']} лет\nХобби: {person['hobby']}", 
            reply_markup=kb
        )
    except Exception as e:
        print(f"Ошибка в поиске: {e}")
        # Если фото упало, хотя бы пришлем текст
        await message.answer(f"✨ {person['name']} (фото загружается...)\nХобби: {person['hobby']}", reply_markup=kb)

@dp.callback_query(F.data == "next")
async def next_girl(c: types.CallbackQuery):
    await c.message.delete()
    await search(c.message)

@dp.callback_query(F.data.startswith("set_"))
async def set_chat(c: types.CallbackQuery):
    uid = c.from_user.id
    data = active_search_cache.get(uid)
    if not data: return
    
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (uid,))
    sys_prompt = f"Ты {data['name']}, тебе {data['age']}. Будь краткой и реалистичной."
    db_query("INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, 1, 15)", 
             (uid, data['name'], data['app'], data['seed'], sys_prompt, json.dumps([])))
    
    await c.message.answer(f"Чат с {data['name']} открыт!", reply_markup=get_chat_kb())
    await c.answer()

@dp.message(F.text == "❤️ Статус")
async def check_status(message: types.Message):
    res = db_query("SELECT girl_name, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (message.from_user.id,), fetchone=True)
    if res: await message.answer(f"Статус с {res[0]}: {res[1]}/100 ❤️")
    else: await message.answer("Нет активного чата.")

@dp.message(F.text == "📇 Контакты")
async def list_contacts(message: types.Message):
    girls = db_query("SELECT DISTINCT girl_name FROM chats WHERE user_id = ?", (message.from_user.id,), fetchall=True)
    if not girls: return await message.answer("Список пуст.")
    
    btns = [[InlineKeyboardButton(text=g[0], callback_data=f"sw_{g[0]}")] for g in girls]
    await message.answer("Твои контакты:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.message()
async def talk(message: types.Message):
    res = db_query("SELECT girl_name, system_prompt, history, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (message.from_user.id,), fetchone=True)
    if not res: return

    name, sys, hist_raw, trust = res
    history = json.loads(hist_raw)
    
    # Очень упрощенный анализ изменения доверия
    change = 2 if len(message.text) > 10 else 1
    new_trust = min(100, trust + change)
    
    history.append({"role": "user", "content": message.text})
    
    response = await groq_client.chat.completions.create(model="llama-3.3-70b-versatile",messages=[{"role":"system","content":f"{sys} Доверие: {new_trust}/100"}] + history[-10:])
    # Добавляем индекс [0]
    answer = response.choices[0].message.content
    history.append({"role": "assistant", "content": answer})
    
    db_query("UPDATE chats SET history = ?, trust_level = ? WHERE user_id = ? AND girl_name = ?", 
             (json.dumps(history), new_trust, message.from_user.id, name))
    await message.answer(answer)

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
