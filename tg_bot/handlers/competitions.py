from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from html import escape
from ai_engine.predictor import AIPredictor
from utils.globals import LEAGUES

router = Router()
predictor = AIPredictor()

async def push_message(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "menu_competitions")
async def select_competition(callback: CallbackQuery):
    keyboard = []
    for league_id, league_info in LEAGUES.items():
        keyboard.append([InlineKeyboardButton(text=league_info['name'], callback_data=f"league_{league_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await push_message(callback, "⚽ <b>Select Competition</b>\nChoose a league to view upcoming matches:", reply_markup)

@router.callback_query(F.data.startswith("league_"))
async def show_matches_for_league(callback: CallbackQuery):
    league_id = int(callback.data.split("_")[1])
    league_name = LEAGUES[league_id]['name']
    
    try:
        fixtures = await predictor.get_upcoming_matches(league_id)
        
        if not fixtures:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Leagues", callback_data="menu_competitions")]
            ])
            await push_message(callback, f"ℹ️ No upcoming fixtures found today for {escape(league_name)}.", keyboard)
            return
            
        keyboard = []
        for f in fixtures[:10]:
            home = f['teams']['home']['name']
            away = f['teams']['away']['name']
            button_text = f"{home} vs {away}"
            fixture_id = f['fixture']['id']
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"match_{fixture_id}")])
            
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Leagues", callback_data="menu_competitions")])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await push_message(callback, f"🏆 <b>{escape(league_name)} Upcoming Matches</b>\nSelect a match:", reply_markup)
        
    except Exception:
        await push_message(callback, "❌ Error fetching matches. Please try again later.")

@router.callback_query(F.data == "menu_live")
async def show_live_matches(callback: CallbackQuery):
    try:
        fixtures = await predictor.get_ongoing_matches()
        if not fixtures:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
            ])
            await push_message(callback, "ℹ️ No matches are currently ongoing.", keyboard)
            return
            
        keyboard = []
        for f in fixtures[:10]:
            home = f['teams']['home']['name']
            away = f['teams']['away']['name']
            status = f['fixture']['status']['short']
            button_text = f"[{status}] {home} vs {away}"
            fixture_id = f['fixture']['id']
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"match_{fixture_id}")])
            
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await push_message(callback, f"🔴 <b>Live Matches</b>\nSelect a match for Live Odds Prediction:", reply_markup)
        
    except Exception:
        await push_message(callback, "❌ Error fetching matches. Please try again later.")

@router.callback_query(F.data == "menu_upcoming")
async def show_upcoming_matches(callback: CallbackQuery):
    try:
        fixtures = await predictor.get_upcoming_matches()
        if not fixtures:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
            ])
            await push_message(callback, "ℹ️ No upcoming matches found for today.", keyboard)
            return
            
        keyboard = []
        for f in fixtures[:10]:
            home = f['teams']['home']['name']
            away = f['teams']['away']['name']
            time = f['fixture']['date'][11:16]
            button_text = f"[{time}] {home} vs {away}"
            fixture_id = f['fixture']['id']
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"match_{fixture_id}")])
            
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
        
        await push_message(callback, f"📅 <b>Upcoming Matches</b>\nSelect a match:", reply_markup)
        
    except Exception:
        await push_message(callback, "❌ Error fetching matches. Please try again later.")

@router.callback_query(F.data.startswith("match_"))
async def select_prediction_type(callback: CallbackQuery):
    fixture_id = int(callback.data.split("_")[1])
    fixtures = await predictor.get_all_matches()
    fixture = next((item for item in fixtures if item['fixture']['id'] == fixture_id), None)

    if not fixture:
        await push_message(callback, "❌ Match not found in live data.")
        return

    home_name = fixture['teams']['home']['name']
    away_name = fixture['teams']['away']['name']
    
    text = (
        f"<b>Match Selected:</b> {escape(home_name)} vs {escape(away_name)}\n\n"
        "Please select the prediction type you'd like:"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠/🚗 Home/Away Only", callback_data=f"type_result_{fixture_id}")],
        [InlineKeyboardButton(text="⚽ Goals Only", callback_data=f"type_goals_{fixture_id}")],
        [InlineKeyboardButton(text="🚩 Corners Only", callback_data=f"type_corners_{fixture_id}")],
        [InlineKeyboardButton(text="🟨 Yellow Cards Only", callback_data=f"type_cards_{fixture_id}")],
        [InlineKeyboardButton(text="🎯 Hybrid (All)", callback_data=f"type_full_{fixture_id}")],
        [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
    ])
    
    await push_message(callback, text, keyboard)
