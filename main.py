import os
import asyncio
import random
import logging
import requests
import io
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

def get_ai_profile():
    seed = random.randint(1, 999999)
    
    # 1. Генерируем текст
    prompt_text = "Generate dating profile: Name, Age (15-40), Hobby. In Russian language."
    text_url = f"https://text.pollinations.ai/prompt/{quote(prompt_text)}?seed={seed}&model=openai"
    
    try:
        res = requests.get(text_url, timeout=10)
        profile_text = res.text.strip() if res.status_code == 200 else "Екатерина, 20 лет."
    except:
        profile_text = "Анастасия, 22 года."

    # 2. Генерируем фото и СКАЧИВАЕМ его
    image_desc = "beautiful young woman portrait, realistic, high quality"
    image_url = f"https://image.pollinations.ai/prompt/{quote(image_desc)}?seed={seed}&width=512&height=512&nologo=true"
    
    logger.info(f"Загрузка фото: {image_url}")
    
    try:
        img_res = requests.get(image_url, timeout=20)
        img_res.raise_for_status()
        # Превращаем байты картинки в файл для отправки
        photo = BufferedInputFile(img_res.content, filename="profile.jpg")
        return photo, profile_text
    except Exception as e:
        logger.error(f"Не удалось скачать фото: {e}")
        return None, profile_text

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Бот готов! Ищи собеседниц.", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Начать поиск")
async def search_handler(message: types.Message):
    status_msg = await message.answer("📡 Генерирую профиль...")
    
    try:
        photo, caption = get_ai_profile()
        
        if photo:
            await message.answer_photo(photo=photo, caption=f"✅ **Найдена:**\n\n{caption}", parse_mode="Markdown")
        else:
            await message.answer(f"✅ **Найдена (без фото):**\n\n{caption}")
            
    except Exception as e:
        logger.error(f"Ошибка в хендлере: {e}")
        await message.answer("❌ Ошибка. Попробуй еще раз.")
    finally:
        await status_msg.delete()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
