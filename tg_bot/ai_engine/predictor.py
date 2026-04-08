import os
import sys
import math
import joblib
import numpy as np

# Add the parent directory to sys.path to import the main AI modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from live_data_fetcher import APIFootballClient
from feature_builder_live import FeatureBuilderLive
from utils.globals import LEAGUES
from services.llm_reasoning import HybridReasoningEngine

class AIPredictor:
    def __init__(self):
        self.reasoning_engine = HybridReasoningEngine()
        self.model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'ultimate_combined_model.pkl'))
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found at {self.model_path}")
            
        self.model_data = joblib.load(self.model_path)
        self.ensemble_model = self.model_data['ensemble']
        
        self.api_football = APIFootballClient()
        self.feature_builder = FeatureBuilderLive(self.model_path)

    async def get_all_matches(self, league_id=None):
        leagues_to_fetch = [league_id] if league_id else list(LEAGUES.keys())
        fixtures = self.api_football.get_todays_fixtures(leagues=leagues_to_fetch)
        return fixtures

    async def get_upcoming_matches(self, league_id=None):
        leagues_to_fetch = [league_id] if league_id else list(LEAGUES.keys())
        fixtures = self.api_football.get_todays_fixtures(leagues=leagues_to_fetch, status_filter='upcoming')
        return fixtures

    async def get_ongoing_matches(self, league_id=None):
        leagues_to_fetch = [league_id] if league_id else list(LEAGUES.keys())
        fixtures = self.api_football.get_todays_fixtures(leagues=leagues_to_fetch, status_filter='ongoing')
        return fixtures

    def _normalize_probs(self, values):
        arr = np.array(values, dtype=float)
        arr = np.clip(arr, 1e-9, None)
        total = arr.sum()
        return arr / total if total else np.array([1 / len(arr)] * len(arr))

    def _team_summary(self, matches, team_id):
        goals_for = []
        goals_against = []
        points = []

        for match in matches:
            is_home = match['teams']['home']['id'] == team_id
            team_goals = match['goals']['home'] if is_home else match['goals']['away']
            opp_goals = match['goals']['away'] if is_home else match['goals']['home']
            winner = match['teams']['home']['winner'] if is_home else match['teams']['away']['winner']

            goals_for.append(team_goals)
            goals_against.append(opp_goals)

            if winner is True:
                points.append(3)
            elif winner is None:
                points.append(1)
            else:
                points.append(0)

        return {
            "goals_for": float(np.mean(goals_for)) if goals_for else 0.0,
            "goals_against": float(np.mean(goals_against)) if goals_against else 0.0,
            "points": float(np.mean(points)) if points else 0.0
        }

    def _poisson_distribution(self, lam, max_goals=12):
        lam = max(float(lam), 0.01)
        return [math.exp(-lam) * (lam ** i) / math.factorial(i) for i in range(max_goals + 1)]

    def _probability_over(self, lam, line):
        floor_line = int(math.floor(line))
        dist = self._poisson_distribution(lam, max_goals=max(12, floor_line + 10))
        under_or_equal = sum(dist[:floor_line + 1])
        return max(0.0, min(1.0, 1.0 - under_or_equal))

    def _estimated_odds(self, probability):
        probability = max(min(float(probability), 0.95), 0.18)
        return round(max(1.18, min(5.5, 1 / probability)), 2)

    def _risk_label(self, confidence, price):
        if confidence >= 74 or price <= 1.55:
            return "Safe"
        if confidence >= 58 or price <= 2.20:
            return "Middle"
        return "Risky"

    def _market_pick(self, category, label, probability, segment, estimated_odds=None):
        confidence = round(float(probability) * 100, 1)
        price = round(float(estimated_odds), 2) if estimated_odds else self._estimated_odds(probability)
        return {
            "category": category,
            "label": label,
            "confidence": confidence,
            "estimated_odds": price,
            "risk_level": self._risk_label(confidence, price),
            "segment": segment
        }

    def _build_result_markets(self, home_team, away_team, combined_probs, odds):
        home_prob = float(combined_probs[1])
        draw_prob = float(combined_probs[2])
        away_prob = float(combined_probs[0])

        markets = [
            self._market_pick("result", f"{home_team} to Win Match", home_prob, "winner", odds.get('home', self._estimated_odds(home_prob))),
            self._market_pick("result", "Match Result: Draw", draw_prob, "draw", odds.get('draw', self._estimated_odds(draw_prob))),
            self._market_pick("result", f"{away_team} to Win Match", away_prob, "winner_alt", odds.get('away', self._estimated_odds(away_prob))),
            self._market_pick("result", f"Double Chance: {home_team} or Draw", home_prob + draw_prob, "double_chance_home"),
            self._market_pick("result", f"Double Chance: {away_team} or Draw", away_prob + draw_prob, "double_chance_away"),
            self._market_pick("result", f"Double Chance: {home_team} or {away_team}", home_prob + away_prob, "double_chance_no_draw"),
            self._market_pick("result", f"{home_team} Draw No Bet (DNB)", home_prob + (draw_prob * 0.35), "dnb_home"),
            self._market_pick("result", f"{away_team} Draw No Bet (DNB)", away_prob + (draw_prob * 0.35), "dnb_away")
        ]

        return markets

    def _build_total_markets(self, category, home_team, away_team, home_lambda, away_lambda, total_lines, team_lines):
        total_lambda = home_lambda + away_lambda
        markets = []

        cat_name = category.capitalize()
        for line in total_lines:
            over_prob = self._probability_over(total_lambda, line)
            under_prob = 1 - over_prob
            markets.append(self._market_pick(category, f"Over {line} Total Match {cat_name}", over_prob, "match_total"))
            markets.append(self._market_pick(category, f"Under {line} Total Match {cat_name}", under_prob, "match_total"))

        for line in team_lines:
            home_over_prob = self._probability_over(home_lambda, line)
            away_over_prob = self._probability_over(away_lambda, line)
            markets.append(self._market_pick(category, f"{home_team} Over {line} Team {cat_name}", home_over_prob, "home_team"))
            markets.append(self._market_pick(category, f"{home_team} Under {line} Team {cat_name}", 1 - home_over_prob, "home_team"))
            markets.append(self._market_pick(category, f"{away_team} Over {line} Team {cat_name}", away_over_prob, "away_team"))
            markets.append(self._market_pick(category, f"{away_team} Under {line} Team {cat_name}", 1 - away_over_prob, "away_team"))

        return markets

    def _build_goal_markets(self, home_team, away_team, home_goals, away_goals):
        markets = self._build_total_markets("goals", home_team, away_team, home_goals, away_goals, [1.5, 2.5, 3.5], [0.5, 1.5, 2.5])
        home_zero = math.exp(-max(home_goals, 0.01))
        away_zero = math.exp(-max(away_goals, 0.01))
        btts_yes = 1 - home_zero - away_zero + (home_zero * away_zero)
        markets.append(self._market_pick("goals", "Both Teams To Score - Yes", btts_yes, "btts"))
        markets.append(self._market_pick("goals", "Both Teams To Score - No", 1 - btts_yes, "btts"))
        return markets

    def _build_corner_markets(self, home_team, away_team, home_corners, away_corners):
        return self._build_total_markets("corners", home_team, away_team, home_corners, away_corners, [8.5, 9.5, 10.5], [3.5, 4.5, 5.5])

    def _build_card_markets(self, home_team, away_team, home_cards, away_cards):
        return self._build_total_markets("cards", home_team, away_team, home_cards, away_cards, [3.5, 4.5, 5.5], [1.5, 2.5, 3.5])

    def _category_summary(self, markets):
        best_by_segment = {}

        for market in markets:
            current = best_by_segment.get(market["segment"])
            if not current or market["confidence"] > current["confidence"]:
                best_by_segment[market["segment"]] = market

        return sorted(best_by_segment.values(), key=lambda item: (-item["confidence"], item["estimated_odds"]))[:4]

    def _pick_for_risk(self, markets, risk_level):
        if risk_level == "Safe":
            valid = [m for m in markets if 1.10 <= m["estimated_odds"] <= 1.50]
            target_odds = 1.30
        elif risk_level == "Middle":
            valid = [m for m in markets if 1.50 < m["estimated_odds"] <= 2.00]
            target_odds = 1.75
        else:
            valid = [m for m in markets if m["estimated_odds"] > 2.00]
            target_odds = 2.50

        pool = valid if valid else markets

        ranked = sorted(
            pool,
            key=lambda item: (
                item["risk_level"] != risk_level if not valid else False,
                abs(item["estimated_odds"] - target_odds),
                -item["confidence"]
            )
        )
        return ranked[0] if ranked else None

    def _combine_model_and_odds(self, model_probs, odds):
        market_probs = self._normalize_probs([
            1 / odds['away'] if odds.get('away') else 0.25,
            1 / odds['home'] if odds.get('home') else 0.4,
            1 / odds['draw'] if odds.get('draw') else 0.3
        ])
        model_strength = float(np.max(model_probs))
        model_weight = 0.7 if model_strength >= 0.6 else 0.62 if model_strength >= 0.5 else 0.55
        combined = self._normalize_probs((model_probs * model_weight) + (market_probs * (1 - model_weight)))
        return market_probs, combined, model_weight

    def _bet_pool_for_type(self, bet_type, markets):
        category = {
            "result": "result",
            "goals": "goals",
            "cards": "cards",
            "corners": "corners"
        }.get(bet_type)

        if not category:
            return markets

        filtered = [market for market in markets if market["category"] == category]
        return filtered if filtered else markets

    def _estimate_fallback_odds(self, home_team, away_team, home_summary, away_summary):
        home_strength = (home_summary["points"] * 0.55) + (home_summary["goals_for"] * 0.3) - (home_summary["goals_against"] * 0.2) + 0.35
        away_strength = (away_summary["points"] * 0.55) + (away_summary["goals_for"] * 0.3) - (away_summary["goals_against"] * 0.2)
        draw_bias = 0.95 - abs(home_strength - away_strength) * 0.18
        scores = np.array([
            max(0.25, away_strength),
            max(0.25, home_strength),
            max(0.22, draw_bias)
        ])
        probs = self._normalize_probs(scores)
        fallback_odds = {
            "home": round(self._estimated_odds(probs[1]), 2),
            "draw": round(self._estimated_odds(probs[2]), 2),
            "away": round(self._estimated_odds(probs[0]), 2)
        }
        fallback_summary = {
            "home": round(probs[1] * 100, 1),
            "draw": round(probs[2] * 100, 1),
            "away": round(probs[0] * 100, 1),
            "reason": f"Estimated from recent form and goal balance for {home_team} and {away_team}"
        }
        return fallback_odds, fallback_summary

    async def get_prediction(self, home_team_name, away_team_name, bet_type="full", fixture_data=None, target_risk=None):
        """
        Generate a prediction ticket for a specific match.
        If target_risk is provided, an ai_reasoning string will be generated for that risk tier's pick.
        """
        try:
            if not fixture_data:
                # Find the fixture from today's matches
                fixtures = await self.get_live_matches()
                for f in fixtures:
                    if (f['teams']['home']['name'].lower() == home_team_name.lower() or 
                        f['teams']['away']['name'].lower() == away_team_name.lower()):
                        fixture_data = f
                        break
            
            if not fixture_data:
                return {"error": f"Could not find a live match for {home_team_name} vs {away_team_name} today."}

            home_team = fixture_data['teams']['home']
            away_team = fixture_data['teams']['away']
            league_id = fixture_data['league']['id']
            fixture_id = fixture_data['fixture']['id']

            home_matches = self.api_football.get_team_last_matches(home_team['id'])
            away_matches = self.api_football.get_team_last_matches(away_team['id'])
            home_summary = self._team_summary(home_matches, home_team['id'])
            away_summary = self._team_summary(away_matches, away_team['id'])
            
            fixture_odds = self.api_football.get_fixture_odds(fixture_id)
            odds = self.api_football.extract_match_winner_odds(fixture_odds)
            odds_source = "api_football"
            fallback_market = None
            
            if not odds or odds['home'] == 0:
                odds, fallback_market = self._estimate_fallback_odds(
                    home_team['name'],
                    away_team['name'],
                    home_summary,
                    away_summary
                )
                odds_source = "estimated"
                
            X = self.feature_builder.build_features(home_matches, away_matches, odds)
            model_probs = self._normalize_probs(self.ensemble_model.predict_proba(X)[0])
            market_probs, combined_probs, model_weight = self._combine_model_and_odds(model_probs, odds)

            labels = ["Away Win", "Home Win", "Draw"]
            pred_idx = int(np.argmax(combined_probs))

            home_form_pts = home_summary["points"]
            away_form_pts = away_summary["points"]
            home_goals_avg = max(0.1, (home_summary["goals_for"] * 0.65) + (away_summary["goals_against"] * 0.35))
            away_goals_avg = max(0.1, (away_summary["goals_for"] * 0.65) + (home_summary["goals_against"] * 0.35))
            total_goals_pred = home_goals_avg + away_goals_avg
            btts_yes = 1 - math.exp(-home_goals_avg) - math.exp(-away_goals_avg) + math.exp(-(home_goals_avg + away_goals_avg))

            home_corners = max(3.0, round(4.2 + (home_goals_avg * 0.9) + (home_form_pts * 0.35), 2))
            away_corners = max(3.0, round(3.8 + (away_goals_avg * 0.9) + (away_form_pts * 0.35), 2))
            home_cards = max(1.0, round(1.4 + (away_form_pts * 0.45) + (home_summary["goals_against"] * 0.25), 2))
            away_cards = max(1.0, round(1.4 + (home_form_pts * 0.45) + (away_summary["goals_against"] * 0.25), 2))

            result_markets = self._build_result_markets(home_team['name'], away_team['name'], combined_probs, odds)
            goal_markets = self._build_goal_markets(home_team['name'], away_team['name'], home_goals_avg, away_goals_avg)
            corner_markets = self._build_corner_markets(home_team['name'], away_team['name'], home_corners, away_corners)
            card_markets = self._build_card_markets(home_team['name'], away_team['name'], home_cards, away_cards)

            all_markets = result_markets + goal_markets + corner_markets + card_markets
            bet_pool = self._bet_pool_for_type(bet_type, all_markets)

            safe_pick = self._pick_for_risk(bet_pool, "Safe")
            middle_pick = self._pick_for_risk(bet_pool, "Middle")
            risky_pick = self._pick_for_risk(bet_pool, "Risky")

            strongest_pick = max(bet_pool, key=lambda item: (item["confidence"], -item["estimated_odds"])) if bet_pool else None
            overall_risk = self._risk_label(float(np.max(combined_probs) * 100), min(odds.values()))
            model_power = round(((float(np.max(model_probs)) * model_weight) + (float(np.max(combined_probs)) * (1 - model_weight))) * 100, 1)

            target_pick = None
            if target_risk == 'Safe':
                target_pick = safe_pick
            elif target_risk == 'Middle':
                target_pick = middle_pick
            elif target_risk == 'Risky':
                target_pick = risky_pick
            else:
                target_pick = strongest_pick

            ai_reasoning = ""
            if target_pick:
                context = {
                    "home_team": home_team['name'],
                    "away_team": away_team['name'],
                    "pick_label": target_pick['label'],
                    "risk_level": target_pick['risk_level'],
                    "home_form": home_form_pts,
                    "away_form": away_form_pts,
                    "model_weight": round(model_weight * 100, 1),
                    "category": target_pick['category']
                }
                ai_reasoning = await self.reasoning_engine.generate_reasoning(context)

            return {
                "success": True,
                "fixture_id": fixture_id,
                "home_team": home_team['name'],
                "away_team": away_team['name'],
                "league": fixture_data['league']['name'],
                "winner": labels[pred_idx],
                "predicted_score": f"{int(round(home_goals_avg))} - {int(round(away_goals_avg))}",
                "confidence": combined_probs[pred_idx] * 100,
                "bet_type": bet_type,
                "ai_reasoning": ai_reasoning,
                "probs": {
                    "home": combined_probs[1] * 100,
                    "draw": combined_probs[2] * 100,
                    "away": combined_probs[0] * 100
                },
                "model_probs": {
                    "home": model_probs[1] * 100,
                    "draw": model_probs[2] * 100,
                    "away": model_probs[0] * 100
                },
                "market_probs": {
                    "home": market_probs[1] * 100,
                    "draw": market_probs[2] * 100,
                    "away": market_probs[0] * 100
                },
                "odds_context": {
                    "source": odds_source,
                    "fallback_market": fallback_market
                },
                "stats": {
                    "home_goals": round(home_goals_avg, 2),
                    "away_goals": round(away_goals_avg, 2),
                    "home_corners": round(home_corners, 1),
                    "away_corners": round(away_corners, 1),
                    "home_cards": round(home_cards, 1),
                    "away_cards": round(away_cards, 1)
                },
                "insights": {
                    "over_2_5": "Yes" if total_goals_pred > 2.5 else "No",
                    "btts": "Yes" if btts_yes > 0.5 else "No",
                    "home_form": round(home_form_pts, 2),
                    "away_form": round(away_form_pts, 2),
                    "model_weight": round(model_weight * 100, 1),
                    "model_power": model_power
                },
                "betting_options": {
                    "safe": safe_pick["label"] if safe_pick else "No safe bet",
                    "medium": middle_pick["label"] if middle_pick else "No middle bet",
                    "high": risky_pick["label"] if risky_pick else "No risky bet"
                },
                "recommendations": {
                    "safe": safe_pick,
                    "middle": middle_pick,
                    "risky": risky_pick,
                    "primary": strongest_pick
                },
                "market_overview": {
                    "result": self._category_summary(result_markets),
                    "goals": self._category_summary(goal_markets),
                    "corners": self._category_summary(corner_markets),
                    "cards": self._category_summary(card_markets)
                },
                "odds": odds,
                "risk_level": overall_risk
            }
            
        except Exception as e:
            import traceback
            print(f"ERROR IN GET PREDICTION:\n{traceback.format_exc()}")
            return {"error": str(e)}
