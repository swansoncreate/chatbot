import os
import asyncio
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

user_contexts = {}

# Клавиатуры
def get_main_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔍 Найти собеседницу")]], resize_keyboard=True)

def get_chat_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Завершить чат")]], resize_keyboard=True)

def get_action_inline():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💌 Написать ей", callback_data="start_chat"),
        InlineKeyboardButton(text="⏭ Следующая", callback_data="next_profile")
    ]])

# === ЛОГИКА ИИ ===
def generate_profile():
    try:
        chat_completion = client.chat.completions.create(
            model="llama-3.1-8b-instant", 
            messages=[{"role": "user", "content": "Придумай анкету девушки: Имя, Возраст, Хобби. Кратко, 2-3 строки."}],
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return "Марина, 21 год. Люблю кофе и кино."

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Добро пожаловать! Ищи анкеты и начинай общение.", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Найти собеседницу")
async def search_handler(message: types.Message):
    profile = generate_profile()
    # Временно сохраняем профиль в памяти, пока юзер не нажал "Написать"
    user_contexts[message.from_user.id] = {"temp_profile": profile}
    
    await message.answer(f"👤 **Новая анкета:**\n\n{profile}", 
                         parse_mode="Markdown", 
                         reply_markup=get_action_inline())

# Кнопка "Написать" (Inline)
@dp.callback_query(F.data == "start_chat")
async def start_chat_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    profile = user_contexts.get(user_id, {}).get("temp_profile", "Собеседница")
    
    # Создаем контекст для Groq
    user_contexts[user_id] = [
        {"role": "system", "content": f"Ты девушка из чата. Твоя анкета: {profile}. Отвечай кратко."},
    ]
    
    await callback.message.answer("✨ Ты начал чат! Можешь писать первое сообщение.", reply_markup=get_chat_kb())
    await callback.answer()

# Кнопка "Следующая" (Inline)
@dp.callback_query(F.data == "next_profile")
async def next_profile_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    await search_handler(callback.message)
    await callback.answer()

# Кнопка "Завершить чат" (Reply)
@dp.message(F.text == "❌ Завершить чат")
async def stop_chat(message: types.Message):
    if message.from_user.id in user_contexts:
        del user_contexts[message.from_user.id]
    await message.answer("Чат завершен. Ищем кого-то другого?", reply_markup=get_main_kb())

# Логика самого чата
@dp.message()
async def chat_handler(message: types.Message):
    user_id = message.from_user.id
    
    # Проверяем, в чате ли юзер (в user_contexts должен быть список сообщений)
    if user_id not in user_contexts or isinstance(user_contexts[user_id], dict):
        return # Если просто пишет текст без активного чата — игнорим

    user_contexts[user_id].append({"role": "user", "content": message.text})

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=user_contexts[user_id],
        )
        ai_reply = response.choices[0].message.content
        user_contexts[user_id].append({"role": "assistant", "content": ai_reply})
        await message.answer(ai_reply)
    except Exception as e:
        await message.answer("⚠️ Ошибка связи.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
