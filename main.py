import asyncio
import random
import sqlite3
import json
import os
import urllib.parse
import sys
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
from groq import AsyncGroq

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_API_KEY:
    print("ОШИБКА: Токены не найдены в переменых окружения!", flush=True)

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
    print("БД Инициализирована", flush=True)

# --- ВСПОМОГАТЕЛЬНОЕ ---
APPEARANCES = ["scandinavian blonde woman", "latin brunette woman", "asian cute girl", "slavic beautiful woman"]

def get_chat_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Выйти", callback_data="exit_chat"),
         InlineKeyboardButton(text="🗑 Удалить чат", callback_data="delete_chat")]
    ])
    
async def generate_ai_personality():
    prompt = ("Create a unique female personality. "
              "Return ONLY JSON: {'name': 'Имя', 'age': 22, 'hobby': 'Хобби на русском', "
              "'photo_style': 'detailed english prompt for image generation focus on appearance and background'}")
    try:
        res = await groq_client.chat.completions.create(
            model="llama-3.1-8b-instant", # Новая рабочая модель
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )    
        data = json.loads(res.choices[0].message.content)
        print(f"Сгенерирована личность: {data['name']}", flush=True)
        return data
    except Exception as e:
        print(f"Ошибка Groq (личность): {e}", flush=True)
        return {"name": "Анна", "age": 21, "hobby": "Фотография", "photo_style": "girl with a camera, cinematic light"}

# --- ОБРАБОТЧИКИ ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔍 Найти пару"), KeyboardButton(text="❤️ Статус")],
        [KeyboardButton(text="📇 Контакты")]
    ], resize_keyboard=True)
    await message.answer("Симулятор запущен! Нажми 'Найти пару', чтобы начать.", reply_markup=kb)

@dp.message(F.text == "🔍 Найти пару")
async def search(message: types.Message):
    # Создаем заглушку на случай ошибки, чтобы код не падал при обращении к переменным
    person = {"name": "Девушка", "age": 20, "hobby": "Общение"} 
    kb = None
    
    try:
        # 1. Используем актуальную модель Llama 3.1
        person = await generate_ai_personality() # Внутри этой функции тоже замени модель на llama-3.1-8b-instant
        app = random.choice(APPEARANCES)
        seed = random.randint(1, 10**9)
        
        # 2. Формируем промпт для фото (только латиница)
        clean_style = person.get('photo_style', 'beautiful face').replace("'", "").replace('"', "")
        full_prompt = f"{app}, {clean_style}, high quality, realistic face"
        encoded_prompt = urllib.parse.quote(full_prompt)
        
        # 3. ЭТАЛОННЫЙ URL (обязательно /prompt/ после домена)
        photo_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?seed={seed}&width=512&height=512&nologo=true"
        
        # Выводим в лог для проверки
        print(f"DEBUG URL: {photo_url}", flush=True)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Начать общение", callback_data=f"set_{seed}")],
            [InlineKeyboardButton(text="⏭ Следующая", callback_data="next")]
        ])
        
        active_search_cache[message.from_user.id] = {**person, "app": app, "seed": seed}

        # 4. Отправка фото
        await message.answer_photo(
            photo=photo_url, 
            caption=f"✨ {person['name']}, {person['age']} лет\nХобби: {person['hobby']}", 
            reply_markup=kb
        )
        
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА В SEARCH: {e}", flush=True)
        # Если фото сломалось, отправляем текст, чтобы бот не «молчал»
        error_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏭ Попробовать еще раз", callback_data="next")]])
        await message.answer(
            f"✨ {person['name']}, {person['age']} лет\n(Фото временно недоступно из-за ошибки API)\nХобби: {person['hobby']}", 
            reply_markup=kb if kb else error_kb
        )

@dp.callback_query(F.data == "next")
async def next_girl(c: types.CallbackQuery):
    await c.message.delete()
    await search(c.message)

@dp.callback_query(F.data.startswith("set_"))
async def set_chat(c: types.CallbackQuery):
    uid = c.from_user.id
    data = active_search_cache.get(uid)
    if not data: 
        return await c.answer("Ошибка: данные устарели. Попробуй найти заново.")
    
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (uid,))
    sys_prompt = f"Ты {data['name']}, тебе {data['age']}. Твое хобби {data['hobby']}. Будь краткой, дерзкой и реалистичной."
    
    db_query("INSERT INTO chats (user_id, girl_name, appearance, seed, system_prompt, history, is_active, trust_level) VALUES (?, ?, ?, ?, ?, ?, 1, 15)", 
             (uid, data['name'], data['app'], data['seed'], sys_prompt, json.dumps([])))
    
    await c.message.answer(f"Чат с {data['name']} открыт! Напиши ей что-нибудь.", reply_markup=get_chat_kb())
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

@dp.callback_query(F.data == "exit_chat")
async def exit_chat(c: types.CallbackQuery):
    db_query("UPDATE chats SET is_active = 0 WHERE user_id = ?", (c.from_user.id,))
    await c.message.answer("Вы вышли в главное меню.")
    await c.answer()

@dp.message()
async def talk(message: types.Message):
    res = db_query("SELECT girl_name, system_prompt, history, trust_level FROM chats WHERE user_id = ? AND is_active = 1", (message.from_user.id,), fetchone=True)
    if not res: return

    name, sys_p, hist_raw, trust = res
    history = json.loads(hist_raw)
    
    # Рост доверия
    change = 2 if len(message.text) > 10 else 1
    new_trust = min(100, trust + change)
    
    history.append({"role": "user", "content": message.text})
    
    try:
        response = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"system","content":f"{sys_p} Уровень симпатии к игроку: {new_trust}/100. Отвечай как живая девушка в мессенджере."}] + history[-8:]
        )
        answer = response.choices[0].message.content
        history.append({"role": "assistant", "content": answer})
        
        db_query("UPDATE chats SET history = ?, trust_level = ? WHERE user_id = ? AND girl_name = ?", 
                 (json.dumps(history), new_trust, message.from_user.id, name))
        await message.answer(answer)
    except Exception as e:
        print(f"Ошибка Groq (talk): {e}", flush=True)

async def main():
    init_db()
    print("Бот запускается...", flush=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
