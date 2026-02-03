import os
import asyncio
import logging
from groq import Groq
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# === НАСТРОЙКИ ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токены из Secrets
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_KEY)

# Хранилище контекста: {user_id: {role_prompt: "...", messages: [...]}}
user_contexts = {}

def get_main_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔍 Найти собеседницу")]], resize_keyboard=True)

# === ЛОГИКА ИИ ===
def generate_profile_and_persona():
    """Генерирует личность через Groq"""
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": "Придумай краткую анкету девушки для чата (Имя, Возраст, Хобби) и опиши её характер в одном предложении."}],
        model="llama3-8b-8192",
    )
    full_text = chat_completion.choices[0].message.content
    return full_text

# === ОБРАБОТЧИКИ ===
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Привет! Нажми кнопку, чтобы найти кого-нибудь для общения.", reply_markup=get_main_kb())

@dp.message(F.text == "🔍 Найти собеседницу")
async def search_handler(message: types.Message):
    profile = generate_profile_and_persona()
    
    # Сохраняем системный промпт, чтобы ИИ понимал, КТО он в этом чате
    user_contexts[message.from_user.id] = [
        {"role": "system", "content": f"Ты — девушка из анонимного чата. Твоя анкета: {profile}. Отвечай кратко, игриво и по-женски. Не пиши как робот."},
    ]
    
    await message.answer(f"✅ **Собеседница найдена!**\n\n{profile}\n\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n*Можешь просто писать сообщения, она ответит.*", parse_mode="Markdown")

@dp.message()
async def chat_handler(message: types.Message):
    user_id = message.from_user.id
    
    if user_id not in user_contexts:
        await message.answer("Сначала нажми 'Найти собеседницу'", reply_markup=get_main_kb())
        return

    # Добавляем сообщение юзера в историю
    user_contexts[user_id].append({"role": "user", "content": message.text})

    try:
        # Запрос к Groq
        response = client.chat.completions.create(
            messages=user_contexts[user_id],
            model="llama3-8b-8192",
        )
        ai_reply = response.choices[0].message.content
        
        # Сохраняем ответ ИИ в историю
        user_contexts[user_id].append({"role": "assistant", "content": ai_reply})
        
        await message.answer(ai_reply)
        
    except Exception as e:
        logger.error(f"Groq Error: {e}")
        await message.answer("⚠️ Собеседница отвлеклась, попробуй еще раз.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
