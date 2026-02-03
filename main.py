import os
import asyncio
import random
import logging
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from urllib.parse import quote

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# === ПОЛУЧЕНИЕ ТОКЕНА ===
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    logger.error("BOT_TOKEN не найден в секретах GitHub!")
    exit("Ошибка: Токен BOT_TOKEN отсутствует.")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# === КЛАВИАТУРА ===
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔍 Начать поиск")]],
        resize_keyboard=True
    )

# === ЛОГИКА ГЕНЕРАЦИИ ===
def get_ai_profile():
    seed = random.randint(1, 999999)
    
    # Текст промпта
    raw_prompt = "Придумай анкету девушки для чата: Имя, Возраст (15-40), Хобби. Пиши кратко на русском."
    
    # Экранируем кириллицу и добавляем пропущенный слэш / после домена
    encoded_prompt = quote(raw_prompt)
    text_url = f"https://text.pollinations.ai/pompt/{encoded_prompt}?seed={seed}"
    
    # Логируем URL для проверки, если снова упадет
    logger.info(f"Запрос к тексту: {text_url}")
    
    response = requests.get(text_url, timeout=15)
    response.raise_for_status()
    profile_text = response.text.strip()

    # Для фото тоже экранируем промпт на всякий случай
    image_raw = "high quality realistic portrait of a beautiful young woman, cinematic lighting"
    image_url = f"https://image.pollinations.ai/pompt/{quote(image_raw)}?seed={seed}&width=512&height=512&nologo=true"
    
    return image_url, profile_text

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "Бот готов к работе. Нажми кнопку для поиска.",
        reply_markup=get_main_kb()
    )

@dp.message(F.text == "🔍 Начать поиск")
async def search_handler(message: types.Message):
    status_msg = await message.answer("⏳ Генерирую личность (это может занять 5-10 сек)...")
    
    try:
        photo_url, caption = get_ai_profile()
        
        await message.answer_photo(
            photo=photo_url,
            caption=f"👤 **Найдена анкета:**\n\n{caption}",
            parse_mode="Markdown"
        )
        logger.info("Анкета успешно сгенерирована и отправлена.")
        
    except Exception as e:
        logger.error(f"Ошибка при генерации анкеты: {e}", exc_info=True)
        await message.answer(f"❌ Произошла ошибка: {type(e).__name__}\nПроверь логи в GitHub Actions.")
    
    finally:
        try:
            await status_msg.delete()
        except:
            pass

# === ЗАПУСК ===
async def main():
    logger.info("Запуск бота...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Критическая ошибка при работе бота: {e}")

if __name__ == "__main__":
    asyncio.run(main())
