import asyncio
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from g4f.client import Client

# ВАЖНО: Токен лучше передавать через переменные окружения (см. ниже)
import os
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()
ai_client = Client()

def get_photo_url():
    seed = random.randint(1, 999999)
    return f"https://image.pollinations.ai{seed}&nologo=true"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = [[types.KeyboardButton(text="🔍 Искать собеседника")]]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("Анонимный чат запущен!", reply_markup=keyboard)

@dp.message(F.text == "🔍 Искать собеседника")
async def search(message: types.Message):
    inline_kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ Дальше", callback_data="search")],
        [types.InlineKeyboardButton(text="✅ Общаться", callback_data="start_chat")]
    ])
    await message.answer_photo(get_photo_url(), caption="Нашли анкету!", reply_markup=inline_kb)

@dp.callback_query(F.data == "search")
async def next_search(callback: types.CallbackQuery):
    await search(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "start_chat")
async def start_chat(callback: types.CallbackQuery):
    await callback.message.answer("Она ждет твоего сообщения...")
    await callback.answer()

@dp.message()
async def talk(message: types.Message):
    # Бесплатный ответ от нейросети
    response = ai_client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": "Ты - девушка 20 лет в анонимном чате. Пиши кратко."},
                  {"role": "user", "content": message.text}]
    )
    await message.answer(response.choices[0].message.content)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
