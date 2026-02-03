import os
import asyncio
import random
import logging
from groq import Groq
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# === ЛОГИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ТОКЕНЫ
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

user_contexts = {}

# === КНОПКИ ===
def get_main_kb():
    # Главная кнопка поиска
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔍 Найти собеседницу")]],
        resize_keyboard=True
    )

def get_chat_kb():
    # Кнопка во время диалога
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Завершить чат")]],
        resize_keyboard=True
    )

def get_action_inline():
    # Кнопки под анкетой
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💌 Написать ей", callback_data="start_chat"),
        InlineKeyboardButton(text="⏭ Следующая", callback_data="next_profile")
    ]])

# === ЛОГИКА ИИ ===
def generate_profile():
    seed = random.randint(1, 999999)
    try:
        chat_completion = client.chat.completions.create(
            model="llama-3.3-70b-specdec", 
            messages=[{"role": "user", "content": "Придумай имя, возраст (18-25) и хобби для девушки. Одной строкой на русском."}],
        )
        # ИСПРАВЛЕНО: Добавлен индекс [0]
        profile_text = chat_completion.choices[0].message.content
        image_url = f"https://image.pollinations.ai{seed}"
        return profile_text, image_url
    except Exception as e:
        logger.error(f"Ошибка ИИ: {e}")
        return "Анна, 20 лет. Люблю музыку.", None

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Жми кнопку, чтобы начать!", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Найти собеседницу")
async def search_handler(message: types.Message):
    profile, photo_url = generate_profile()
    # Сохраняем временный профиль
    user_contexts[message.from_user.id] = {"temp_profile": profile}
    
    if photo_url:
        await message.answer_photo(
            photo=photo_url,
            caption=f"👤 **Анкета:**\n\n{profile}",
            reply_markup=get_action_inline()
        )
    else:
        await message.answer(f"👤 **Анкета:**\n\n{profile}", reply_markup=get_action_inline())

@dp.callback_query(F.data == "start_chat")
async def start_chat(callback: types.CallbackQuery):
    uid = callback.from_user.id
    profile = user_contexts.get(uid, {}).get("temp_profile", "Собеседница")
    
    # Инициализируем диалог
    user_contexts[uid] = [
        {"role": "system", "content": f"Ты девушка {profile}. Пиши кратко, по-русски, как в чате."}
    ]
    
    await callback.message.answer("✨ Начинай общение!", reply_markup=get_chat_kb())
    await callback.answer()

@dp.callback_query(F.data == "next_profile")
async def next_profile(callback: types.CallbackQuery):
    await callback.message.delete()
    await search_handler(callback.message)
    await callback.answer()

@dp.message(F.text == "❌ Завершить чат")
async def stop_chat(message: types.Message):
    user_contexts.pop(message.from_user.id, None)
    await message.answer("Ищем дальше?", reply_markup=get_main_kb())

@dp.message()
async def chat_handler(message: types.Message):
    uid = message.from_user.id
    # Проверка: если юзер не в чате (а просто прислал текст)
    if uid not in user_contexts or isinstance(user_contexts[uid], dict):
        return

    user_contexts[uid].append({"role": "user", "content": message.text})
    
    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-specdec",
            messages=user_contexts[uid]
        )
        ans = res.choices[0].message.content
        user_contexts[uid].append({"role": "assistant", "content": ans})
        await message.answer(ans)
    except:
        await message.answer("Ой, я отвлеклась. Что?")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
