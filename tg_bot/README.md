# Football AI Telegram Bot

This is a Telegram bot that interfaces with the `ultimate_combined_model.pkl` to generate real-time AI football predictions and betting tickets.

## Features
- **Registration Flow:** Users must register (saves to SQLite DB) before accessing the bot.
- **Competition Selection:** Browse live matches categorized by top European leagues.
- **Detailed Bet Types:** Choose to predict Match Result, Goals, Cards, Corners, or get a Full AI Ticket.
- **AI Recommended Games:** The bot automatically finds the best value bets of the day and builds an Accumulator Ticket.
- **My History:** View your previously generated and saved betting tickets.

## Setup Instructions

1. **Navigate to the bot directory:**
   ```bash
   cd tg_bot
   ```

2. **Install requirements:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure your `.env` file:**
   - Ensure your `.env` file contains your Telegram Bot Token, API-Football key, and Odds-API key.

4. **Run the bot:**
   ```bash
   python bot.py
   ```

## Folder Structure

```
tg_bot/
├── bot.py                  # Main entry point (aiogram setup)
├── requirements.txt        # Dependencies (aiogram, aiosqlite, etc.)
├── .env                    # Your actual configuration
├── README.md               # Instructions
├── ai_engine/
│   └── predictor.py        # AI model wrapper and feature builder
├── database/
│   └── db.py               # SQLite database setup and queries
├── handlers/
│   ├── registration.py     # /start and registration logic
│   ├── menu.py             # Main menu navigation
│   ├── competitions.py     # League and match selection
│   └── predictions.py      # Bet type selection and ticket generation
└── utils/
    └── globals.py          # Shared constants (e.g., LEAGUES dict)
```