from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from ai_engine.predictor import AIPredictor
from database.db import save_ticket
import logging
from html import escape

router = Router()
predictor = AIPredictor()
logger = logging.getLogger(__name__)

async def push_message(callback: CallbackQuery, text: str, reply_markup=None):
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    if text:
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode='HTML')
    await callback.answer()

@router.callback_query(F.data.startswith("type_"))
async def select_risk_level(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    bet_type = data_parts[1]
    fixture_id = data_parts[2]
    
    text = (
        "Please select your risk profile for this prediction:\n"
        "<i>(Safe: 1.1-1.50 | Medium: 1.50-2.00 | Risky: 2.00+)</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡️ Safe Ticket", callback_data=f"risk_Safe_{bet_type}_{fixture_id}")],
        [InlineKeyboardButton(text="⚖️ Middle Ticket", callback_data=f"risk_Middle_{bet_type}_{fixture_id}")],
        [InlineKeyboardButton(text="🔥 Risky Ticket", callback_data=f"risk_Risky_{bet_type}_{fixture_id}")],
        [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
    ])
    
    await push_message(callback, text, keyboard)

@router.callback_query(F.data.startswith("risk_"))
async def handle_risk_selection(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    tier = data_parts[1]
    bet_type = data_parts[2]
    fixture_id = int(data_parts[3])

    try:
        fixtures = await predictor.get_all_matches()
        fixture_data = next((f for f in fixtures if f['fixture']['id'] == fixture_id), None)

        if not fixture_data:
            await push_message(callback, "❌ Match not found in live data.")
            return

        prediction = await predictor.get_prediction(
            fixture_data['teams']['home']['name'],
            fixture_data['teams']['away']['name'],
            bet_type,
            fixture_data,
            target_risk=tier
        )

        if "error" in prediction:
            logger.error(f"Prediction internal error: {prediction['error']}")
            await push_message(callback, f"❌ Error: {escape(prediction['error'])}")
            return

        await send_detailed_ticket(callback, prediction, tier)

    except Exception as e:
        import traceback
        logger.error(f"Prediction error:\n{traceback.format_exc()}")
        await push_message(callback, "❌ An error occurred while generating the prediction.")

async def send_detailed_ticket(callback: CallbackQuery, p: dict, selected_risk: str):
    
    # Grab the target pick based on the user's risk selection
    target_pick = None
    if selected_risk == 'Safe':
        target_pick = p['recommendations'].get('safe')
    elif selected_risk == 'Middle':
        target_pick = p['recommendations'].get('middle')
    elif selected_risk == 'Risky':
        target_pick = p['recommendations'].get('risky')

    if not target_pick:
         await push_message(callback, f"❌ No viable {escape(selected_risk)} pick found for this match.")
         return

    ticket = (
        "🎟️ <b>AI BETTING TICKET</b>\n\n"
        f"<b>Match:</b> {escape(p['home_team'])} vs {escape(p['away_team'])}\n"
        f"<b>Competition:</b> {escape(p['league'])}\n"
        f"<b>Ticket Profile:</b> {escape(selected_risk.upper())}\n\n"
        f"🎯 <b>Prediction:</b> {escape(target_pick['label'])}\n"
        f"📈 <b>Odds (Est):</b> {target_pick['estimated_odds']:.2f}\n"
        f"✨ <b>Confidence:</b> {target_pick['confidence']:.1f}%\n\n"
        "💡 <b>AI Reasoning:</b>\n"
        f"{escape(p.get('ai_reasoning', 'Reasoning generated internally.'))}\n\n"
        "<b>Model + Odds Metrics</b>\n"
        f"Model Power: {p['insights']['model_power']:.1f}/100\n"
        f"Model Weight: {p['insights']['model_weight']:.1f}%\n"
        f"Score Projection: {escape(p['predicted_score'])}\n"
    )

    if p['odds_context'].get('fallback_market'):
        ticket += (
            f"Estimated odds basis: {escape(p['odds_context']['fallback_market']['reason'])}\n"
        )

    await save_ticket(
        user_id=callback.from_user.id,
        match=f"{p['home_team']} vs {p['away_team']}",
        bet_type="full",
        prediction=target_pick['label'],
        confidence=target_pick['confidence'],
        risk_level=selected_risk
    )

    keyboard = [
        [InlineKeyboardButton("🔄 Pick Another Match", callback_data="menu_competitions")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await push_message(callback, ticket, reply_markup)

@router.callback_query(F.data == "menu_recommended")
async def handle_recommended_prompt(callback: CallbackQuery):
    text = (
        "📊 <b>AI Accumulator Ticket</b>\n\n"
        "Please select the prediction type for the accumulator:"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠/🚗 Home/Away Only", callback_data="acctype_result")],
        [InlineKeyboardButton(text="⚽ Goals Only", callback_data="acctype_goals")],
        [InlineKeyboardButton(text="🚩 Corners Only", callback_data="acctype_corners")],
        [InlineKeyboardButton(text="🟨 Yellow Cards Only", callback_data="acctype_cards")],
        [InlineKeyboardButton(text="🎯 Hybrid (All)", callback_data="acctype_full")],
        [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
    ])
    await push_message(callback, text, keyboard)

@router.callback_query(F.data.startswith("acctype_"))
async def handle_accumulator_risk_prompt(callback: CallbackQuery):
    bet_type = callback.data.split("_")[1]
    text = (
        "📊 <b>AI Accumulator Ticket</b>\n\n"
        "Please select your risk profile for the accumulator:\n"
        "<i>(Safe: 1.1-1.50 | Medium: 1.50-2.00 | Risky: 2.00+)</i>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛡️ Safe Accumulator", callback_data=f"acc_Safe_{bet_type}")],
        [InlineKeyboardButton(text="⚖️ Middle Accumulator", callback_data=f"acc_Middle_{bet_type}")],
        [InlineKeyboardButton(text="🔥 Risky Accumulator", callback_data=f"acc_Risky_{bet_type}")],
        [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
    ])
    await push_message(callback, text, keyboard)

@router.callback_query(F.data.startswith("acc_"))
async def handle_accumulator_gen(callback: CallbackQuery):
    parts = callback.data.split("_")
    tier = parts[1]
    bet_type = parts[2]
    
    # Notify user that generation is running since it takes multiple api calls
    await callback.message.edit_text("⏳ Generating Accumulator Ticket using hybrid logic...", reply_markup=None)

    try:
        fixtures = await predictor.get_upcoming_matches()
        if not fixtures:
            await push_message(callback, "ℹ️ No upcoming fixtures found today to generate an accumulator.")
            return

        acc_matches = fixtures[:15]
        candidate_lines = []

        for fixture in acc_matches:
            home = fixture['teams']['home']
            away = fixture['teams']['away']
            pred = await predictor.get_prediction(home['name'], away['name'], bet_type, fixture, target_risk=tier)

            if "error" not in pred:
                pick = pred['recommendations'].get(tier.lower())
                if pick:
                    candidate_lines.append((
                        pick['confidence'],
                        f"🔸 <b>{escape(home['name'])} vs {escape(away['name'])}</b>\n"
                        f"↳ Pick: {escape(pick['label'])} (Odds: {pick['estimated_odds']:.2f})\n"
                        f"↳ Reasoning: {escape(pred.get('ai_reasoning', ''))}"
                    ))

        ticket_lines = [line for _, line in sorted(candidate_lines, reverse=True)[:3]]

        if not ticket_lines:
            await push_message(callback, f"❌ Could not generate enough confident {tier} predictions for an accumulator.")
            return

        ticket = (
            f"🎟️ <b>AI ACCUMULATOR TICKET ({tier.upper()})</b>\n\n"
            "Here are the top AI recommended bets:\n\n" +
            "\n\n".join(ticket_lines)
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
        ])

        await push_message(callback, ticket, keyboard)

    except Exception as e:
        logger.error(f"Accumulator error: {e}")
        await push_message(callback, "❌ An error occurred while generating the accumulator.")

@router.callback_query(F.data == "menu_history")
async def handle_history(callback: CallbackQuery):
    from database.db import get_user_history
    history = await get_user_history(callback.from_user.id)

    if not history:
        await push_message(
            callback,
            "📜 You have no saved tickets in your history.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")]])
        )
        return

    history_text = "📜 <b>Your Recent Tickets</b>\n\n"
    for match, bet_type, pred, conf, risk, created in history:
        history_text += f"🗓 {escape(created[:10])} | <b>{escape(match)}</b>\n"
        history_text += f"↳ Prediction: {escape(pred)} ({conf:.1f}%)\n"
        history_text += f"↳ Risk: {escape(risk)}\n\n"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")]
    ])

    await push_message(callback, history_text, keyboard)
