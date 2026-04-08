import asyncio
import sys
import os
sys.path.append(os.path.abspath('tg_bot'))
from tg_bot.ai_engine.predictor import AIPredictor
from live_data_fetcher import APIFootballClient

async def test_it():
    print("Initializing Predictor...")
    predictor = AIPredictor()
    print("Fetching matches...")
    fixtures = await predictor.get_upcoming_matches()
    if not fixtures:
        print("No matches found.")
        return
        
    f = fixtures[0]
    fixture_id = f['fixture']['id']
    print(f"Testing match {f['teams']['home']['name']} vs {f['teams']['away']['name']}, ID: {fixture_id}")
    
    print("Calling gets_prediction...")
    prediction = await predictor.get_prediction(
        f['teams']['home']['name'],
        f['teams']['away']['name'],
        "full",
        f,
        target_risk="Safe"
    )
    print("Prediction Result keys:")
    print(prediction.keys() if isinstance(prediction, dict) else type(prediction))
    if "error" in prediction:
        print("Error returned:", prediction["error"])
    else:
        print("Success! Keys:")
        for k, v in prediction.items():
            if k not in ['probs', 'model_probs', 'market_probs', 'odds', 'market_overview', 'stats']:
                print(f"  {k}: {v}")

if __name__ == "__main__":
    asyncio.run(test_it())
