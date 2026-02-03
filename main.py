import os
import asyncio
import random
import logging
import requests
from urllib.parse import quote
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔍 Начать поиск")]],
        resize_keyboard=True
    )

# === ЛОГИКА ===
def get_ai_profile():
    seed = random.randint(1, 999999)
    
    # Исправленный эндпоинт (openai - самый стабильный у них сейчас)
    # Запрашиваем на английском, чтобы не было проблем с кодировкой, но просим русский ответ
    prompt = "Generate a short dating profile for a girl: Name, Age (18-25), Hobby. Response language: Russian."
    text_url = f"https://text.pollinations.ai{quote(prompt)}?seed={seed}&model=openai"
    
    try:
        logger.info(f"Запрос к тексту: {text_url}")
        response = requests.get(text_url, timeout=15)
        
        if response.status_code != 200:
            logger.warning(f"Сервер текста выдал {response.status_code}, использую заглушку")
            profile_text = "Екатерина, 22 года. Люблю путешествия и живое общение!"
        else:
            profile_text = response.text.strip()
    except Exception as e:
        logger.error(f"Ошибка сети при запросе текста: {e}")
        profile_text = "Анастасия, 19 лет. Рисую и смотрю кино."

    # Картинка (prompt на английском для лучшего качества)
    image_prompt = "beautiful young woman portrait, natural light, realistic photography"
    image_url = f"https://image.pollinations.ai{quote(image_prompt)}?seed={seed}&width=1024&height=1024&nologo=true"
    
    return image_url, profile_text

# === HANDLERS ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привет! Нажми на кнопку ниже, чтобы найти анкету.", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Начать поиск")
async def search_handler(message: types.Message):
    status_msg = await message.answer("🔍 Ищу в базе данных...")
    
    try:
        photo_url, caption = get_ai_profile()
        await message.answer_photo(
            photo=photo_url,
            caption=f"👤 **Анкета найдена:**\n\n{caption}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Общий сбой: {e}", exc_info=True)
        await message.answer("❌ Сервер временно перегружен. Попробуй еще раз через пару секунд.")
    finally:
        await status_msg.delete()

async def main():
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
