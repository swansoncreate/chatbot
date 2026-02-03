import os
import asyncio
import random
import logging
from groq import Groq
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

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

# === КНОПКИ ===
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Главное меню")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Инфо")]
        ], 
        resize_keyboard=True
    )

def get_chat_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎤 Начать чат")],
            [KeyboardButton(text="❌ Выйти")]
        ], 
        resize_keyboard=True
    )

def get_action_inline():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data="delete")]
        ]
    )

# === ЛОГИКА ИИ ===
def generate_profile():
    try:
        chat_completion = client.chat.completions.create(
            model=MODEL_NAME, 
            messages=[{"role": "user", "content": "Придумай имя, возраст (18-25) и хобби для девушки. Одной короткой строкой на русском."}],
        )
        return chat_completion.choices.message.content
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
    user_contexts[message.from_user.id] = {"temp_profile": profile}
    
    # ИСПРАВЛЕНО: Добавлена main_kb, чтобы она не пропадала
    await message.answer(f"👤 **Анкета:**\n\n{profile}", reply_markup=get_action_inline())

@dp.callback_query(F.data == "start_chat")
async def start_chat(callback: types.CallbackQuery):
    uid = callback.from_user.id
    profile = user_contexts.get(uid, {}).get("temp_profile", "Собеседница")
    
    user_contexts[uid] = [
        {"role": "system", "content": f"Ты — девушка {profile}. Пиши как реальный человек в чате: кратко, на русском, со смайликами. Никакой официальщины."}
    ]
    
    try:
        res = client.chat.completions.create(
            model=MODEL_NAME,
            messages=user_contexts[uid] + [{"role": "user", "content": "Напиши приветствие."}]
        )
        first_msg = res.choices.message.content
        user_contexts[uid].append({"role": "assistant", "content": first_msg})
        await callback.message.answer(first_msg, reply_markup=get_chat_kb())
    except:
        await callback.message.answer("Приветик! 😊", reply_markup=get_chat_kb())
        
    await callback.answer()

@dp.callback_query(F.data == "next_profile")
async def next_profile(callback: types.CallbackQuery):
    await callback.message.delete()
    # ИСПРАВЛЕНО: При смене профиля вызываем хендлер, который отправит нужную клаву
    await search_handler(callback.message)
    await callback.answer()

@dp.message(F.text == "❌ Завершить чат")
async def stop_chat(message: types.Message):
    user_contexts.pop(message.from_user.id, None)
    await message.answer("Чат завершен. Ищем дальше?", reply_markup=get_main_kb())

@dp.message()
async def chat_handler(message: types.Message):
    uid = message.from_user.id
    if uid not in user_contexts or isinstance(user_contexts[uid], dict):
        return

    user_contexts[uid].append({"role": "user", "content": message.text})
    
    try:
        res = client.chat.completions.create(model=MODEL_NAME, messages=user_contexts[uid])
        ans = res.choices.message.content
        user_contexts[uid].append({"role": "assistant", "content": ans})
        await message.answer(ans)
    except Exception as e:
        logger.error(f"Ошибка чата: {e}")
        await message.answer("Я на секунду отвлеклась, повтори? 😇")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
