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

# --- ЛОГИКА ГЕНЕРАЦИИ ---

APPEARANCES = [
    "scandinavian beauty, blonde hair, blue eyes",
    "mediterranean, wavy dark hair, brown eyes",
    "slavic, chestnut hair, green eyes",
    "latin style, curly black hair, tan skin"
]

async def generate_ai_personality():
    """Генерирует уникальную личность через ИИ Groq"""
    prompt = "Придумай случайную девушку: Имя, Возраст (18-40), Хобби. Верни ТОЛЬКО JSON: {'name': '..', 'age': .., 'hobby': '..'}"
    try:
        res = await groq_client.chat.completions.create(
            model="llama3-8b-8192", 
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(res.choices.message.content)
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
    app = random.choice(APPEARANCES)
    seed = random.randint(1, 10**9)
    
    photo_url = f"https://image.pollinations.ai_{app.replace(' ', '_')}_age_{person['age']}?seed={seed}&model=flux"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Начать чат с {person['name']}", callback_data=f"set_{seed}")],
        [InlineKeyboardButton(text="👎 Дальше", callback_data="next")]
    ])
    
    active_search_cache[message.from_user.id] = {**person, "app": app, "seed": seed}
    await message.answer_photo(photo=photo_url, caption=f"✨ {person['name']}, {person['age']} лет\nУвлекается: {person['hobby']}", reply_markup=kb)

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
    sys_prompt = f"Ты {data['name']}, тебе {data['age']}. Хобби: {data['hobby']}. Внешность: {data['app']}."
    db_query("INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, 1, 15)", 
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

    # Память на факты
    f_prompt = f"Извлеки факты о юзере из: '{message.text}'. Верни JSON {{'ключ':'значение'}} или {{}}."
    try:
        f_res = await groq_client.chat.completions.create(model="llama3-8b-8192", messages=[{"role":"user","content":f_prompt}])
        new_facts = json.loads(f_res.choices.message.content)
        for k,v in new_facts.items(): db_query("INSERT OR REPLACE INTO user_facts VALUES (?, ?, ?)", (uid, k, v))
    except: pass

    all_f = db_query("SELECT fact_key, fact_value FROM user_facts WHERE user_id = ?", (uid,), fetchall=True)
    facts_str = ", ".join([f"{f[0]}:{f[1]}" for f in all_f])

    # Доверие
    try:
        ans = await groq_client.chat.completions.create(model="llama3-8b-8192", messages=[{"role":"user","content":f"User:'{message.text}'. Friendly:+5, Rude:-10. Number only."}])
        change = int(''.join(filter(lambda x: x in "-0123456789", ans.choices.message.content)))
    except: change = 1
    
    new_trust = max(0, min(100, trust + change))
    db_query("UPDATE chats SET trust_level = ? WHERE user_id = ? AND girl_name = ?", (new_trust, uid, name))

    # Ответ
    mood = "сдержанная" if new_trust < 40 else "игривая" if new_trust < 80 else "влюбленная"
    prompt = f"{sys} {get_time_context()} Твой настрой: {mood}. Ты знаешь о юзере: {facts_str}. Пиши кратко."

    await bot.send_chat_action(message.chat.id, "typing")
    response = await groq_client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"system","content":prompt}] + history[-6:] + [{"role":"user","content":message.text}])
    answer = response.choices.message.content

    await asyncio.sleep(min(max(1.5, len(answer)*0.03), 4))
    await message.answer(answer)

    # Фото (20% шанс при росте доверия)
    if new_trust > trust and random.random() < 0.2:
        loc = "home_selfie" if new_trust > 75 else "cafe_portrait"
        url = f"https://image.pollinations.ai_{app.replace(' ','_')}_{loc}?seed={seed}&model=flux"
        await asyncio.sleep(1.5); await message.answer_photo(url, caption="😊")

    history.append({"role":"user","content":message.text})
    history.append({"role":"assistant","content":answer})
    db_query("UPDATE chats SET history = ? WHERE user_id = ? AND girl_name = ?", (json.dumps(history[-10:]), uid, name))

async def main():
    init_db(); await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
