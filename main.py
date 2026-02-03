import os
import asyncio
import random
import logging
import requests
import io
import time
from urllib.parse import quote
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_main_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔍 Начать поиск")]], resize_keyboard=True)

# Функция для скачивания с повторами
def download_image(url, attempts=3):
    for i in range(attempts):
        try:
            res = requests.get(url, timeout=20)
            if res.status_code == 200:
                return res.content
            logger.warning(f"Попытка {i+1}: Сервер вернул {res.status_code}")
        except Exception as e:
            logger.error(f"Попытка {i+1}: Ошибка сети: {e}")
        time.sleep(1) # Ждем секунду перед повтором
    return None

def get_ai_profile():
    seed = random.randint(1, 999999)
    
    # Текст (используем модель поиска, она часто стабильнее)
    prompt_text = "Придумай краткую анкету девушки: Имя, Возраст, Хобби."
    text_url = f"https://text.pollinations.ai/prompt/{quote(prompt_text)}?seed={seed}&model=search"
    
    try:
        res = requests.get(text_url, timeout=15)
        profile_text = res.text.strip() if res.status_code == 200 else "Алина, 21 год. Люблю музыку."
    except:
        profile_text = "Мария, 23 года. Обожаю спорт."

    # Фото (максимально простая ссылка)
    image_desc = "beautiful young woman portrait"
    image_url = f"https://image.pollinations.ai/prompt/{quote(image_desc)}?seed={seed}"
    
    logger.info(f"Загрузка фото: {image_url}")
    img_data = download_image(image_url)
    
    if img_data:
        return BufferedInputFile(img_data, filename="photo.jpg"), profile_text
    return None, profile_text

# === HANDLERS ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Бот готов! Жми кнопку.", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Начать поиск")
async def search_handler(message: types.Message):
    status_msg = await message.answer("📡 Ищу собеседницу...")
    
    try:
        photo, caption = get_ai_profile()
        if photo:
            await message.answer_photo(photo=photo, caption=f"✅ **Найдена:**\n\n{caption}", parse_mode="Markdown")
        else:
            await message.answer(f"✅ **Найдена (фото загружается):**\n\n{caption}")
    except Exception as e:
        logger.error(f"Ошибка в боте: {e}")
        await message.answer("❌ Сервер занят, попробуй еще раз через мгновение.")
    finally:
        try: await status_msg.delete()
        except: pass

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
