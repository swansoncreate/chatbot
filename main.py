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

# === ЛОГИКА ГЕНЕРАЦИИ ===
def get_ai_profile():
    seed = random.randint(1, 999999)
    
    # 1. ТЕКСТ (добавили явный слэш перед prompt)
    prompt_text = "Generate dating profile: Name, Age (15-40), Hobby. In Russian language."
    # ВАЖНО: слэш / после .ai/ ОБЯЗАТЕЛЕН
    text_url = f"https://text.pollinations.ai/{quote(prompt_text)}?seed={seed}&model=openai"
    
    try:
        logger.info(f"Запрос текста: {text_url}")
        res = requests.get(text_url, timeout=10)
        profile_text = res.text.strip() if res.status_code == 200 else "Екатерина, 20 лет. Люблю музыку."
    except:
        profile_text = "Анастасия, 22 года. Обожаю спорт."

    # 2. ФОТО (упростили промпт для стабильности URL)
    image_desc = "beautiful young woman portrait"
    # Ссылка должна быть максимально простой для Telegram
    image_url = f"https://image.pollinations.ai/{quote(image_desc)}?seed={seed}&width=512&height=512&nologo=true"
    
    logger.info(f"Запрос фото: {image_url}")
    return image_url, profile_text

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Бот запущен. Нажми кнопку!", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Начать поиск")
async def search_handler(message: types.Message):
    status_msg = await message.answer("📡 Ищу собеседницу...")
    
    try:
        photo_url, caption = get_ai_profile()
        
        # Отправляем фото
        await message.answer_photo(
            photo=photo_url,
            caption=f"✅ **Найдена:**\n\n{caption}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer("❌ Ошибка связи с ИИ. Попробуй еще раз.")
    finally:
        await status_msg.delete()

async def main():
    # Удаляем вебхуки, чтобы убрать ошибку Conflict
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
