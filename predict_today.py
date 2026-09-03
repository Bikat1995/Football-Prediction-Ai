import os
import joblib
import numpy as np
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
from live_data_fetcher import APIFootballClient
from feature_builder_live import FeatureBuilderLive

LEAGUES = {
    # Europe - Top 5
    "comp_3039": {"name": "Premier League"},
    "comp_8814": {"name": "LaLiga"},
    "comp_4643": {"name": "Bundesliga"},
    "comp_5840": {"name": "Serie A"},
    "comp_0256": {"name": "Ligue 1"},
    # Europe - Major
    "comp_8385": {"name": "Liga Portugal"},
    "comp_3809": {"name": "Eredivisie"},
    "comp_8321": {"name": "Championship"},
    "comp_6387": {"name": "Scottish Premiership"},
    "comp_4893": {"name": "Austrian Bundesliga"},
    # Europe - Cups & Competitions
    "comp_3498": {"name": "Champions League"},
    "comp_7739": {"name": "Europa League"},
    "comp_408698": {"name": "Conference League"},
    "comp_7915": {"name": "Copa del Rey"},
    "comp_8525": {"name": "Coppa Italia"},
    "comp_8531": {"name": "Belgian Pro League"},
    "comp_4750": {"name": "Coupe de France"},
    "comp_3620": {"name": "DFB Pokal"},
    "comp_2504": {"name": "EFL Cup (Carabao)"},
    "comp_7428": {"name": "FA Cup"},
    "comp_1047": {"name": "KNVB Beker"},
    "comp_3861": {"name": "Scottish Cup"},
    "comp_0406": {"name": "2. Bundesliga"},
    "comp_9777": {"name": "Ligue 2"},
    "comp_5450": {"name": "Serie B"},
    "comp_0196": {"name": "League One"},
    "comp_4023": {"name": "League Two"},
    "comp_7218": {"name": "Challenger Pro League"},
    "comp_5749": {"name": "Copa América"},
    "comp_6107": {"name": "FIFA World Cup"},
    # Americas
    "comp_9799": {"name": "MLS"},
    "comp_4795": {"name": "Brasileirão Série A"},
    "comp_5242": {"name": "Copa do Brasil"},
    # Other
    "comp_8363": {"name": "Ukrainian Premier League"},
    "comp_9639": {"name": "Romanian Super Liga"},
    "comp_5824": {"name": "Russian Premier League"},
}

MODEL_FILE = 'ultimate_combined_model.pkl'

def generate_report(predictions):
    """Prints a beautiful summary report for today's predictions"""
    print("\n" + "="*70)
    print(f"TODAY'S PREDICTIONS - {datetime.now().strftime('%A, %d %B %Y')}")
    print("   Powered by TheStatsAPI + Your Trained ML Model")
    print("="*70)
    
    if not predictions:
        print("\n   No predictions found for today.")
        return

    for p in predictions:
        print(f"\nMATCH: {p['home_team']} vs {p['away_team']}")
        print(f"   {p['league']}  |  {p['kickoff']} GMT")
        print(f"   " + "-"*37)
        
        # Determine Prediction Label
        probs = p['probs'] # [Away Win, Home Win, Draw] based on result mapping (0, 1, 2)
        # Prob index mapping: 0=Away, 1=Home, 2=Draw
        labels = ["AWAY WIN", "HOME WIN", "DRAW"]
        pred_idx = np.argmax(probs)
        pred_label = labels[pred_idx]
        pred_team = p['home_team'] if pred_idx == 1 else (p['away_team'] if pred_idx == 0 else "")
        
        print(f"   AI PREDICTION: {pred_label} ({pred_team})")
        print(f"   Confidence: Home {probs[1]:.1%} | Draw {probs[2]:.1%} | Away {probs[0]:.1%}")
        
        # Odds and Value Analysis
        odds = p['odds']
        implied_home = 1 / odds['home'] if odds['home'] else 0
        value_edge = probs[1] - implied_home
        
        print(f"\n   LIVE ODDS (Bet365):")
        print(f"      {p['home_team']}: {odds['home']:.2f} | Draw: {odds['draw']:.2f} | {p['away_team']}: {odds['away']:.2f}")
        
        if value_edge > 0.05:
            print(f"      Value Edge: {p['home_team']} +{value_edge:.1%} STRONG VALUE BET")
        
        print(f"\n   WHY THIS PREDICTION:")
        # Display some key stats used in the feature building
        home_form = p['stats']['home_form']
        away_form = p['stats']['away_form']
        print(f"   {p['home_team']} FORM (last 6): {home_form:.2f} pts/game")
        print(f"   {p['away_team']} FORM (last 6): {away_form:.2f} pts/game")
        
        print(f"\n   " + "-"*37)

    print("\n" + "="*70)

def main():
    print("Starting Daily Predictions Engine...")
    
    # 1. Initialize Clients
    api_client = APIFootballClient()
    feature_builder = FeatureBuilderLive(MODEL_FILE)
    
    # 2. Load ML Model
    if not os.path.exists(MODEL_FILE):
        print(f"Error: Model file {MODEL_FILE} not found!")
        return
    
    model_data = joblib.load(MODEL_FILE)
    ensemble_model = model_data['ensemble']
    
    # 3. Fetch Today's Fixtures
    print(f"Fetching fixtures for {len(LEAGUES)} leagues...")
    fixtures = api_client.get_todays_fixtures(leagues=list(LEAGUES.keys()))
    
    if not fixtures:
        print("No fixtures found for today in the configured leagues.")
        return

    print(f"Found {len(fixtures)} fixtures. Processing predictions...")
    
    all_predictions = []
    
    for fixture in fixtures:
        home_team = fixture['home_team']
        away_team = fixture['away_team']
        league_name = fixture.get('competition_name', LEAGUES.get(fixture['competition_id'], {}).get('name', 'Unknown'))
        fixture_id = fixture['id']
        kickoff_time = datetime.fromisoformat(fixture['utc_date'].replace('Z', '+00:00')).strftime('%H:%M')
        
        print(f"  Processing: {home_team['name']} vs {away_team['name']} ({league_name})")
        
        # 4. Fetch Team Form (last 6 matches)
        home_matches = api_client.get_team_last_matches(home_team['id'])
        away_matches = api_client.get_team_last_matches(away_team['id'])
        
        fixture_odds = api_client.get_fixture_odds(fixture_id)
        odds = api_client.extract_match_winner_odds(fixture_odds)

        if not odds or odds['home'] == 0:
            odds = {'home': 2.1, 'draw': 3.4, 'away': 3.8}
            
        # 6. Build Feature Vector
        try:
            X = feature_builder.build_features(home_matches, away_matches, odds)
            
            # 7. Predict
            # ensemble_model.predict_proba returns probabilities for [0, 1, 2] classes
            # based on ultimate_combined_ai.py: mapping={'H': 1, 'D': 2, 'A': 0}
            probs = ensemble_model.predict_proba(X)[0]
            
            # Store prediction data
            prediction_data = {
                'home_team': home_team['name'],
                'away_team': away_team['name'],
                'league': league_name,
                'kickoff': kickoff_time,
                'probs': probs,
                'odds': odds,
                'stats': {
                    'home_form': np.mean([3 if m['teams']['home']['winner'] else (1 if m['teams']['home']['winner'] is None else 0) for m in home_matches]) if home_matches else 0,
                    'away_form': np.mean([3 if m['teams']['away']['winner'] else (1 if m['teams']['away']['winner'] is None else 0) for m in away_matches]) if away_matches else 0
                }
            }
            all_predictions.append(prediction_data)
            
        except Exception as e:
            print(f"  Error predicting {home_team['name']} vs {away_team['name']}: {e}")

    # 8. Generate and print report
    generate_report(all_predictions)

if __name__ == "__main__":
    main()
