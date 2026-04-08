from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from database.db import is_user_registered, register_user
from handlers.menu import show_main_menu
from html import escape

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    if await is_user_registered(user_id):
        await message.answer("Welcome back to your AI Betting Assistant! 🤖⚽")
        await show_main_menu(message)
    else:
        welcome_text = (
            f"Hello {escape(message.from_user.first_name)}! 👋\n\n"
            "I am your <b>AI Football Betting Assistant</b>.\n"
            "I use advanced Machine Learning (XGBoost + Random Forest) trained on over 8 years of historical match data to provide highly accurate betting predictions.\n\n"
            "To get started, please register by clicking the button below."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Register", callback_data="register_user")]
        ])
        
        await message.answer(welcome_text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "register_user")
async def process_registration(callback: CallbackQuery):
    user = callback.from_user
    await register_user(user.id, user.username, user.first_name)
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("✅ Registration successful! Welcome aboard.")
    await show_main_menu(callback.message)
    await callback.answer()
