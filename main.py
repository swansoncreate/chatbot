import asyncio
import random
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from g4f.client import AsyncClient  # Используем асинхронный клиент

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()
ai_client = AsyncClient()

def get_photo_url():
    # Правильный формат: /prompt/{описание}?seed={число}
    seed = random.randint(1, 999999)
    prompt = "girl, portrait, realistic, 20 years old"
    return f"https://image.pollinations.ai/prompt/{prompt}?seed={seed}&nologo=true"

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
    # Отправляем фото по ссылке
    await message.answer_photo(
        photo=get_photo_url(), 
        caption="Нашли анкету!", 
        reply_markup=inline_kb
    )

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
    # Показываем, что бот "печатает"
    await bot.send_chat_action(message.chat.id, action="typing")
    
    try:
        # Асинхронный запрос к нейросети
        response = await ai_client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты - девушка 20 лет в анонимном чате. Пиши кратко."},
                {"role": "user", "content": message.text}
            ]
        )
        answer = response.choices[0].message.content
        await message.answer(answer)
    except Exception as e:
        await message.answer("Ой, я задумалась... Попробуй еще раз!")
        print(f"Ошибка AI: {e}")

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
