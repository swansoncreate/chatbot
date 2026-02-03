import os
import asyncio
import random
import requests
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# === ПОЛУЧЕНИЕ ТОКЕНА ИЗ SECRETS ===
# В локальной среде можно создать файл .env или экспортировать переменную в терминале
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    exit("Ошибка: Токен BOT_TOKEN не найден в переменных окружения!")

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
    
    # Текстовый промпт
    text_prompt = "Придумай анкету девушки для чата: Имя, Возраст (18-25), Хобби. Пиши кратко на русском."
    text_url = f"https://text.pollinations.ai{text_prompt}?seed={seed}"
    
    try:
        response = requests.get(text_url, timeout=10)
        profile_text = response.text.strip()
    except:
        profile_text = "Екатерина, 21 год. Обожаю музыку."

    # Ссылка на фото
    image_prompt = "high quality realistic portrait of a beautiful young woman, cinematic lighting"
    image_url = f"https://image.pollinations.ai{image_prompt}?seed={seed}&width=512&height=512&nologo=true"
    
    return image_url, profile_text

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "Бот запущен! Нажми кнопку для поиска анкеты.",
        reply_markup=get_main_kb()
    )

@dp.message(F.text == "🔍 Начать поиск")
async def search_handler(message: types.Message):
    status_msg = await message.answer("⏳ Генерирую личность...")
    
    try:
        photo_url, caption = get_ai_profile()
        await message.answer_photo(
            photo=photo_url,
            caption=f"👤 **Собеседница найдена:**\n\n{caption}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await message.answer("Упс, что-то пошло не так...")
    finally:
        await status_msg.delete()

# === ЗАПУСК ===
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
