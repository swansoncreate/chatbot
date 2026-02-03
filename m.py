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
    user_contexts[message.from_user.id] = {"temp_profile": profile}
    
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
        # ИСПРАВЛЕНО: Правильный доступ к контенту ответа
        first_msg = res.choices[0].message.content
        user_contexts[uid].append({"role": "assistant", "content": first_msg})
        await callback.message.answer(first_msg, reply_markup=get_chat_kb())
    except:
        await callback.message.answer("Приветик! 😊", reply_markup=get_chat_kb())
        
    await callback.answer()

@dp.callback_query(F.data == "next_profile")
async def next_profile(callback: types.CallbackQuery):
    await callback.message.delete()
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
        # ИСПРАВЛЕНО: Правильный доступ к контенту ответа
        ans = res.choices[0].message.content
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
