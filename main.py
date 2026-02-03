import os
import asyncio
import random
import logging
from groq import Groq
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Токены из Secrets GitHub
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

if not BOT_TOKEN or not GROQ_KEY:
    exit("ОШИБКА: Проверь BOT_TOKEN и GROQ_API_KEY в Secrets!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

# Хранилище диалогов
user_contexts = {}

# === КЛАВИАТУРЫ ===
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
    seed = random.randint(1, 999999)
    try:
        # Генерируем описание через более умную модель 70b
        chat_completion = client.chat.completions.create(
            model="llama-3.3-70b-specdec", 
            messages=[{"role": "user", "content": "Придумай имя, возраст (18-25) и краткое хобби для девушки. Пиши только это, одной строкой на русском."}],
        )
        profile_text = chat_completion.choices.message.content
        image_url = f"https://image.pollinations.ai{seed}"
        return profile_text, image_url
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return "Мария, 21 год. Люблю спорт и музыку.", None

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привет! Я — анонимный чат. Ищи анкеты и общайся с ИИ-собеседницами.", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Найти собеседницу")
async def search_handler(message: types.Message):
    profile, photo_url = generate_profile()
    user_contexts[message.from_user.id] = {"temp_profile": profile}
    
    if photo_url:
        await message.answer_photo(
            photo=photo_url,
            caption=f"👤 **Найдена анкета:**\n\n{profile}",
            reply_markup=get_action_inline(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(f"👤 **Найдена анкета:**\n\n{profile}", reply_markup=get_action_inline())

@dp.callback_query(F.data == "start_chat")
async def start_chat_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    profile = user_contexts.get(user_id, {}).get("temp_profile", "Мария, 21 год")
    
    # Системный промпт для "живого" русского языка
    user_contexts[user_id] = [
        {"role": "system", "content": (
            f"Ты девушка по имени {profile}. Ты общаешься в анонимном чате в Telegram. "
            "Твой стиль: живой разговорный русский, используй смайлики, пиши кратко. "
            "Не будь официальной, отвечай как реальный человек, немного кокетничай. "
            "Используй сленг типа 'приветик', 'норм', 'ясно'. Не извиняйся как ИИ."
        )},
    ]
    
    await callback.message.answer("✨ Ты начал чат! Напиши что-нибудь своей новой знакомой.", reply_markup=get_chat_kb())
    await callback.answer()

@dp.callback_query(F.data == "next_profile")
async def next_profile_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    await search_handler(callback.message)
    await callback.answer()

@dp.message(F.text == "❌ Завершить чат")
async def stop_chat(message: types.Message):
    if message.from_user.id in user_contexts:
        del user_contexts[message.from_user.id]
    await message.answer("Чат завершен. Ищем новую собеседницу?", reply_markup=get_main_kb())

@dp.message()
async def chat_handler(message: types.Message):
    user_id = message.from_user.id
    
    # Проверка, что юзер в режиме чата (в словаре лежит список сообщений, а не временный профиль)
    if user_id not in user_contexts or isinstance(user_contexts[user_id], dict):
        return

    user_contexts[user_id].append({"role": "user", "content": message.text})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-specdec",
            messages=user_contexts[user_id],
            temperature=0.85
        )
        ai_reply = response.choices[0].message.content
        user_contexts[user_id].append({"role": "assistant", "content": ai_reply})
        await message.answer(ai_reply)
    except Exception as e:
        logger.error(f"Groq Error: {e}")
        await message.answer("⚠️ Связь оборвалась... Напиши еще раз.")

async def main():
    # Удаляем вебхуки и старые сообщения, чтобы не было конфликтов
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
