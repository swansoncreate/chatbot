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

# --- РАБОТА С БД ---
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

# --- ЛОГИКА ГЕНЕРАЦИИ ---

APPEARANCE_TYPES = [
    "scandinavian beauty, ash blonde hair, blue eyes, light freckles",
    "mediterranean girl, wavy dark hair, olive skin, deep brown eyes",
    "slavic girl, straight chestnut hair, green eyes, high cheekbones",
    "asian style, silky black hair, soft features, dark eyes"
]

def get_time_context():
    hour = datetime.now().hour
    if 5 <= hour < 12: return "Сейчас утро. Ты только проснулась, сонная и милая."
    if 12 <= hour < 18: return "Сейчас день. Ты занята делами, отвечаешь бодро."
    if 18 <= hour < 23: return "Сейчас вечер. Ты отдыхаешь, настроена на общение."
    return "Сейчас глубокая ночь. Ты хочешь спать, общение может быть личным."

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти пару")],
        [KeyboardButton(text="📇 Мои контакты"), KeyboardButton(text="❤️ Статус")]
    ], resize_keyboard=True)
    await message.answer("Бот запущен. Ищи собеседниц и развивай отношения!", reply_markup=kb)

@dp.message(F.text == "🔍 Найти пару")
async def search(message: types.Message):
    name = random.choice(["Алина", "Маша", "Лера", "Кристина", "Соня", "Даша"])
    appearance = random.choice(APPEARANCE_TYPES)
    seed = random.randint(1, 10**9)
    
    # Генерация первого фото (прогулка)
    photo_url = f"https://image.pollinations.ai_{appearance.replace(' ', '_')}_walking_outside?seed={seed}&width=1024&height=1024&model=flux"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Общаться с {name}", callback_data=f"setup_{name}_{seed}")],
        [InlineKeyboardButton(text="👎 Дальше", callback_data="next_search")]
    ])
    
    # Сохраняем временные данные внешности в callback_data (или через доп. логику, тут упростим)
    active_search_desc[message.from_user.id] = {"name": name, "app": appearance, "seed": seed}
    await message.answer_photo(photo=photo_url, caption=f"{name}. Описание: {appearance}.", reply_markup=kb)

active_search_desc = {}

@dp.callback_query(F.data == "next_search")
async def next_search(callback: types.CallbackQuery):
    await callback.message.delete()
    await search(callback.message)

@dp.callback_query(F.data.startswith("setup_"))
async def setup_chat(callback: types.CallbackQuery):
    uid = callback.from_user.id
    data = active_search_desc.get(uid)
    if not data: return
    
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (uid,))
    db_query("INSERT INTO chats VALUES (?, ?, ?, ?, ?, ?, 1, 10)", 
             (uid, data['name'], data['app'], data['seed'], 
              f"Ты {data['name']}. Внешность: {data['app']}.", json.dumps([])))
    
    await callback.message.answer(f"Ты начал чат с {data['name']}! Напиши ей.")
    await callback.answer()

@dp.message(F.text == "❤️ Статус")
async def check_status(message: types.Message):
    res = db_query("SELECT girl_name, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (message.from_user.id,), fetchone=True)
    if res:
        await message.answer(f"Твой статус с {res[0]}: {res[1]}/100 ❤️")
    else:
        await message.answer("Сначала найди собеседницу!")

@dp.message(F.text == "📇 Мои контакты")
async def list_contacts(message: types.Message):
    girls = db_query("SELECT DISTINCT girl_name FROM chats WHERE user_id = ?", (message.from_user.id,), fetchall=True)
    if not girls: return await message.answer("Список пуст.")
    btns = [[InlineKeyboardButton(text=f"💬 {n[0]}", callback_data=f"switch_{n[0]}")] for n in girls]
    await message.answer("Выбери, кому написать:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

@dp.callback_query(F.data.startswith("switch_"))
async def switch_chat(callback: types.CallbackQuery):
    name = callback.data.split("_")[1]
    uid = callback.from_user.id
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (uid,))
    db_query("UPDATE chats SET is_active = 1 WHERE user_id = ? AND girl_name = ?", (uid, name))
    await callback.message.answer(f"Переключено на {name}.")
    await callback.answer()

@dp.message()
async def talk(message: types.Message):
    uid = message.from_user.id
    res = db_query("SELECT girl_name, appearance, seed, system_prompt, history, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (uid,), fetchone=True)
    if not res: return

    name, app, seed, sys, hist_raw, trust = res
    history = json.loads(hist_raw)

    # 1. Анализ отношения
    analysis = await groq_client.chat.completions.create(model="llama3-8b-8192", messages=[{"role": "user", "content": f"User said: '{message.text}'. If friendly +5, if mean -10. Return only number."}])
    try: change = int(''.join(filter(lambda x: x in "-1234567890", analysis.choices[0].message.content)))
    except: change = 1
    
    new_trust = max(0, min(100, trust + change))
    db_query("UPDATE chats SET trust_level = ? WHERE user_id = ? AND girl_name = ? AND is_active = 1", (new_trust, uid, name))

    # 2. Ответ ИИ
    time_ctx = get_time_context()
    mood = "холодная" if new_trust < 30 else "дружелюбная" if new_trust < 70 else "влюбленная"
    prompt = f"{sys} {time_ctx} Твое отношение: {mood} (доверие {new_trust}/100)."

    await bot.send_chat_action(message.chat.id, "typing")
    response = await groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": prompt}] + history[-8:] + [{"role": "user", "content": message.text}]
    )
    answer = response.choices[0].message.content

    # Пауза и отправка
    await asyncio.sleep(min(max(1.5, len(answer)*0.04), 5))
    await message.answer(answer)

    # 3. Генерация фото при росте доверия (шанс 20%)
    if new_trust > trust and random.random() < 0.2:
        loc = "cozy_bedroom_selfie" if new_trust > 70 else "sitting_in_cafe"
        photo_url = f"https://image.pollinations.ai_{app.replace(' ', '_')}_{loc}?seed={seed}&width=1024&height=1024&model=flux"
        await asyncio.sleep(2)
        await message.answer_photo(photo_url, caption="Смотри, что скинуть решила... 😊")

    history.append({"role": "user", "content": message.text})
    history.append({"role": "assistant", "content": answer})
    db_query("UPDATE chats SET history = ? WHERE user_id = ? AND girl_name = ? AND is_active = 1", (json.dumps(history[-10:]), uid, name))

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
