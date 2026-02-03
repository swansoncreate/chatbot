import os
import asyncio
import random
import logging
from groq import Groq
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import json

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

# Актуальная модель Groq
MODEL_NAME = "llama-3.3-70b-versatile"

user_contexts = {}

def db_query(sql, params=(), fetchone=False, commit=False):
    with sqlite3.connect("simulator.db") as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        if commit: conn.commit()
        if fetchone: return cursor.fetchone()
        return cursor.fetchall()

# Создаем таблицы при запуске
db_query('''CREATE TABLE IF NOT EXISTS users 
            (user_id INTEGER PRIMARY KEY, profile TEXT, context TEXT)''', commit=True)

def get_main_kb():
    """
    Клавиатура, которая появляется внизу экрана (Reply), для поиска анкет.
    """
    # Создаем кнопку
    button_search = KeyboardButton(text="🔍 Найти собеседницу")
    
    # Собираем в ряд (список списков: [[кнопка]])
    keyboard_layout = [[button_search]]
    
    # Создаем и возвращаем объект клавиатуры
    return ReplyKeyboardMarkup(
        keyboard=keyboard_layout, 
        resize_keyboard=True, # Делает кнопки компактными
        one_time_keyboard=False # Клавиатура остается на месте
    )


def get_chat_kb():
    """
    Клавиатура, которая появляется во время активного чата (Reply), для выхода.
    """
    button_end = KeyboardButton(text="❌ Завершить чат")
    keyboard_layout = [[button_end]]
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard_layout,
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_action_inline():
    """
    Кнопки, встроенные в сообщение с анкетой (Inline), для выбора действия.
    """
    # Кнопки с данными для обработки
    button_write = InlineKeyboardButton(text="💌 Написать ей", callback_data="start_chat")
    button_next = InlineKeyboardButton(text="⏭ Следующая", callback_data="next_profile")
    
    # Собираем в один ряд
    keyboard_layout = [[button_write, button_next]]
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_layout)
    
# === ЛОГИКА ИИ ===
def generate_profile():
    try:
        chat_completion = client.chat.completions.create(
            model=MODEL_NAME, 
            messages=[{"role": "user", "content": "Придумай имя, возраст (18-25) и хобби для девушки. Одной короткой строкой на русском."}],
        )
        # ИСПРАВЛЕНО: Правильный доступ к контенту ответа
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка ИИ (профиль): {e}")
        return "Мария, 21 год. Люблю приключения."

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Бот готов! Жми кнопку поиска.", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Найти собеседницу")
async def search_handler(message: types.Message):
    profile = generate_profile()
    # Сохраняем только профиль, контекст пока пуст
    db_query("INSERT OR REPLACE INTO users (user_id, profile, context) VALUES (?, ?, ?)", 
             (message.from_user.id, profile, None), commit=True)
    
    await message.answer(f"👤 **Анкета:**\n\n{profile}", reply_markup=get_action_inline())

@dp.callback_query(F.data == "start_chat")
async def start_chat(callback: types.CallbackQuery):
    uid = callback.from_user.id
    row = db_query("SELECT profile FROM users WHERE user_id = ?", (uid,), fetchone=True)
    profile = row[0] if row else "Мария, 21 год"
    
    initial_context = [
        {"role": "system", "content": f"Ты — девушка {profile}. Пиши кратко, со смайликами."}
    ]
    
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=initial_context + [{"role": "user", "content": "Напиши приветствие."}]
        )
        first_msg = res.choices[0].message.content
        initial_context.append({"role": "assistant", "content": first_msg})
        
        # Сохраняем обновленный контекст в БД
        db_query("UPDATE users SET context = ? WHERE user_id = ?", 
                 (json.dumps(initial_context), uid), commit=True)
        
        await callback.message.answer(first_msg, reply_markup=get_chat_kb())
    except Exception as e:
        logger.error(f"Ошибка старта: {e}")
        await callback.message.answer("Приветик! 😊", reply_markup=get_chat_kb())
    await callback.answer()

@dp.callback_query(F.data == "next_profile")
async def next_profile(callback: types.CallbackQuery):
    await callback.message.delete()
    await search_handler(callback.message)
    await callback.answer()

@dp.message(F.text == "❌ Завершить chat")
async def stop_chat(message: types.Message):
    db_query("DELETE FROM users WHERE user_id = ?", (message.from_user.id,), commit=True)
    await message.answer("Чат завершен. Ищем дальше?", reply_markup=get_main_kb())

@dp.message()
async def chat_handler(message: types.Message):
    uid = message.from_user.id
    row = db_query("SELECT context FROM users WHERE user_id = ?", (uid,), fetchone=True)
    
    if not row or row[0] is None:
        return # Чат не активен

    context = json.loads(row[0])
    context.append({"role": "user", "content": message.text})
    
    # Ограничиваем историю (последние 10 сообщений + системный промпт), чтобы не переполнять БД
    if len(context) > 11:
        context = [context[0]] + context[-10:]

    try:
        await bot.send_chat_action(message.chat.id, "typing")
        res = client.chat.completions.create(model=MODEL_NAME, messages=context)
        ans = res.choices[0].message.content
        context.append({"role": "assistant", "content": ans})
        
        db_query("UPDATE users SET context = ? WHERE user_id = ?", 
                 (json.dumps(context), uid), commit=True)
        await message.answer(ans)
    except Exception as e:
        logger.error(f"Ошибка чата: {e}")
        await message.answer("Связь прервалась... Повторишь? ⚡️")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
