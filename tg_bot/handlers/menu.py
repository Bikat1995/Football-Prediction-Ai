from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

async def show_main_menu(message: Message):
    menu_text = (
        "🏆 <b>MAIN MENU</b>\n\n"
        "What would you like to do today?\n\n"
        "📊 <b>AI Accumulator Ticket</b> - Get an AI-generated accumulator ticket\n"
        "⚽ <b>Choose League</b> - Browse matches by specific league\n"
        "🔴 <b>Live Odds Prediction</b> - Predictions for currently ongoing matches\n"
        "📅 <b>Upcoming Matches</b> - Browse future fixtures\n"
        "❓ <b>Help & History</b> - Information and past predictions"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 AI Accumulator Ticket", callback_data="menu_recommended")],
        [InlineKeyboardButton(text="⚽ Choose League", callback_data="menu_competitions")],
        [InlineKeyboardButton(text="🔴 Live Odds Prediction", callback_data="menu_live")],
        [InlineKeyboardButton(text="📅 Upcoming Matches", callback_data="menu_upcoming")],
        [InlineKeyboardButton(text="❓ Help & History", callback_data="menu_help")]
    ])
    
    await message.answer(menu_text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "menu_help")
async def process_help(callback: CallbackQuery):
    help_text = (
        "🛠️ <b>Available Options</b>\n\n"
        "⚽ <b>Select Competition</b> - Choose a league and pick a match to get a detailed AI prediction ticket.\n"
        "📊 <b>AI Recommended</b> - The AI will automatically find the best matches today and create an accumulator ticket.\n"
        "📜 <b>My History</b> - View tickets you have saved previously.\n\n"
        "If you encounter any issues, please type /start to reset."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
    ])
    
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(help_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    await show_main_menu(callback.message)
    await callback.answer()
