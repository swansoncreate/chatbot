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
    # Таблица чатов (внешность, сид, доверие)
    db_query("""CREATE TABLE IF NOT EXISTS chats 
                (user_id INTEGER, girl_name TEXT, appearance TEXT, seed INTEGER, 
                system_prompt TEXT, history TEXT, is_active INTEGER, trust_level INTEGER)""")
    # Таблица фактов (память)
    db_query("CREATE TABLE IF NOT EXISTS user_facts (user_id INTEGER, fact_key TEXT, fact_value TEXT)")

# --- ЛОГИКА ГЕНЕРАЦИИ ---

APPEARANCES = [
    "scandinavian beauty, ash blonde hair, blue eyes, light freckles",
    "mediterranean girl, wavy dark hair, olive skin, deep brown eyes",
    "slavic girl, straight chestnut hair, green eyes, high cheekbones",
    "latin style, curly black hair, tan skin, dark eyes"
]

def get_time_context():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Сейчас утро, ты только проснулась, сонная и милая."
    if 12 <= hour < 18: return "Сейчас день, ты занимаешься делами, отвечаешь бодро."
    if 18 <= hour < 23: return "Сейчас вечер, ты отдыхаешь, настроена на общение."
    return "Сейчас глубокая ночь. Ты хочешь спать, общение может быть личным."

def create_typo(text):
    words = text.split()
    if len(words) < 4: return None, None
    idx = random.randint(0, len(words) - 1)
    word = words[idx]
    if len(word) > 4:
        i = random.randint(1, len(word) - 2)
        typo_word = word[:i] + word[i+1] + word[i] + word[i+2:]
        return text.replace(word, typo_word), word
    return None, None

async def extract_facts(user_id, text):
    """Скрытый анализ фактов о пользователе"""
    prompt = f"Извлеки факты о юзере (имя, хобби, питомцы, работа) из текста: '{text}'. Верни JSON {{'ключ': 'значение'}} или {{}}."
    try:
        res = await groq_client.chat.completions.create(model="llama3-8b-8192", messages=[{"role": "user", "content": prompt}])
        facts = json.loads(res.choices[0].message.content)
        for k, v in facts.items():
            db_query("INSERT OR REPLACE INTO user_facts VALUES (?, ?, ?)", (user_id, k, v))
    except: pass

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти пару")],
        [KeyboardButton(text="📇 Контакты"), KeyboardButton(text="❤️ Статус")]
    ], resize_keyboard=True)
    await message.answer("Бот-симулятор запущен! Ищи анкеты и общайся.", reply_markup=kb)

active_search_cache = {}

@dp.message(F.text == "🔍 Найти пару")
async def search(message: types.Message):
    name = random.choice(["Алина", "Кристина", "Маша", "Лера", "Соня", "Юля"])
    app = random.choice(APPEARANCES)
    seed = random.randint(1, 10**9)
    
    photo_url = f"https://image.pollinations.ai_{app.replace(' ', '_')}?seed={seed}&model=flux"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Начать чат с {name}", callback_data=f"set_{name}_{seed}")],
        [InlineKeyboardButton(text="👎 Дальше", callback_data="next")]
    ])
    
    active_search_cache[message.from_user.id] = {"name": name, "app": app, "seed": seed}
    await message.answer_photo(photo=photo_url, caption=f"Это {name}. Она ждет знакомства!", reply_markup=kb)

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
    db_query("INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, 1, 15)", 
             (uid, data['name'], data['app'], data['seed'], 
              f"Ты {data['name']}. Твоя внешность: {data['app']}.", json.dumps([])))
    
    await c.message.answer(f"Чат с {data['name']} открыт! Напиши ей что-нибудь.")
    await c.answer()

@dp.message(F.text == "❤️ Статус")
async def check_status(message: types.Message):
    res = db_query("SELECT girl_name, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (message.from_user.id,), fetchone=True)
    if res:
        await message.answer(f"Твой уровень доверия с {res[0]}: {res[1]}/100 ❤️")
    else:
        await message.answer("Сначала выбери собеседницу в поиске!")

@dp.message(F.text == "📇 Контакты")
async def list_contacts(message: types.Message):
    girls = db_query("SELECT DISTINCT girl_name FROM chats WHERE user_id = ?", (message.from_user.id,), fetchall=True)
    if not girls: return await message.answer("Список пуст.")
    btns = [[InlineKeyboardButton(text=f"💬 {n[0]}", callback_data=f"sw_{n[0]}")] for n in girls]
    await message.answer("Выбери чат:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("sw_"))
async def switch_chat(c: types.CallbackQuery):
    name = c.data.split("_")[1]
    uid = c.from_user.id
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (uid,))
    db_query("UPDATE chats SET is_active = 1 WHERE user_id = ? AND girl_name = ?", (uid, name))
    await c.message.answer(f"Переключено на {name}.")
    await c.answer()

@dp.message()
async def talk(message: types.Message):
    uid = message.from_user.id
    res = db_query("SELECT girl_name, appearance, seed, system_prompt, history, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (uid,), fetchone=True)
    if not res: return

    name, app, seed, sys, hist_raw, trust = res
    history = json.loads(hist_raw)

    # Запускаем память и анализ отношения
    asyncio.create_task(extract_facts(uid, message.text))
    
    facts = db_query("SELECT fact_key, fact_value FROM user_facts WHERE user_id = ?", (uid,), fetchall=True)
    facts_str = ", ".join([f"{f[0]}: {f[1]}" for f in facts])

    # Анализ изменения доверия
    try:
        analysis = await groq_client.chat.completions.create(model="llama3-8b-8192", messages=[{"role": "user", "content": f"User: '{message.text}'. If nice +5, if rude -10. Number only."}])
        change = int(''.join(filter(lambda x: x in "-0123456789", analysis.choices[0].message.content)))
    except: change = 1
    
    new_trust = max(0, min(100, trust + change))
    db_query("UPDATE chats SET trust_level = ? WHERE user_id = ? AND girl_name = ? AND is_active = 1", (new_trust, uid, name))

    # Ответ ИИ
    mood = "сдержанная" if new_trust < 30 else "игривая" if new_trust < 75 else "влюбленная"
    prompt = f"{sys} {get_time_context()} Твое отношение: {mood} (доверие {new_trust}/100). Ты помнишь о нем: {facts_str}. Пиши кратко."

    await bot.send_chat_action(message.chat.id, "typing")
    response = await groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": prompt}] + history[-8:] + [{"role": "user", "content": message.text}]
    )
    answer = response.choices[0].message.content

    # Пауза и опечатки
    await asyncio.sleep(min(max(1.5, len(answer)*0.04), 5))
    typo_text, correct = create_typo(answer)
    if typo_text and random.random() < 0.15:
        await message.answer(typo_text)
        await asyncio.sleep(1)
        await message.answer(f"{correct}*")
    else:
        await message.answer(answer)

    # Фото при росте доверия
    if new_trust > trust and random.random() < 0.2:
        loc = "home_selfie" if new_trust > 70 else "cafe_portrait"
        photo_url = f"https://image.pollinations.ai_{app.replace(' ', '_')}_{loc}?seed={seed}&model=flux"
        await asyncio.sleep(2)
        await message.answer_photo(photo_url, caption="Просто селфи для тебя... ✨")

    history.append({"role": "user", "content": message.text})
    history.append({"role": "assistant", "content": answer})
    db_query("UPDATE chats SET history = ? WHERE user_id = ? AND girl_name = ? AND is_active = 1", (json.dumps(history[-10:]), uid, name))

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
