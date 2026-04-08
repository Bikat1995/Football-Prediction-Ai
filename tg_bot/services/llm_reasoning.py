import os
import requests
import logging

logger = logging.getLogger(__name__)

class HybridReasoningEngine:
    """
    Combines Short-Term Momentum (Live API Data) with 
    Long-Term Pedigree (Custom Model data) to generate natural explanations.
    """
    def __init__(self):
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")

    def _generate_deterministic_logic(self, match_context: dict) -> str:
        """
        Generates a robust deterministic explanation based on the difference
        between recent form and the model's historical backing.
        """
        home = match_context['home_team']
        away = match_context['away_team']
        pick = match_context['pick_label']
        risk = match_context['risk_level']
        home_form = match_context['home_form']
        away_form = match_context['away_form']
        model_weight = match_context['model_weight']
        category = match_context.get('category', 'result')

        # Form string
        better_form = home if home_form > away_form else away
        poorer_form = away if home_form > away_form else home
        
        reasoning = f"According to API-Football short-term momentum, {better_form} has superior recent match rating compared to {poorer_form}. "
        
        # Risk Logic
        if risk == "Safe":
            reasoning += f"This pick ({pick}) is classified as SAFE. "
        elif risk == "Middle":
            reasoning += f"This pick ({pick}) is classified as MIDDLE. "
        else:
            reasoning += f"This pick ({pick}) involves higher variance and is considered RISKY. "

        # Synthesis Rule
        if model_weight >= 60.0:
            reasoning += f"The trained model strongly favors this outcome historically, contributing {model_weight}% weight to the decision over short-term trends. "
        else:
            reasoning += f"The historical model validates this, but short-term odds dynamics also play a significant factor. "
            
        if "Goals" in pick or "Score" in pick:
            reasoning += f"Combining the historical offensive volume with recent attacking streaks mathematically supports this goal angle."
        elif "Corners" in pick:
            reasoning += f"Based on historical tactical data, the custom model indicates a strong tendency for set-pieces and cornerspam against this type of defense."
        elif "Cards" in pick or "Yellow" in pick:
            reasoning += f"With the custom model factoring in big-match pressure and defensive vulnerabilities, card markets provide excellent value here."
        else:
             reasoning += f"Historically, the selected team shows immense pedigree in matches of this profile."

        return reasoning

    def _call_llm_api(self, prompt: str) -> str:
        """Attempt to call Gemini or OpenAI to refine the text if keys exist."""
        if self.openai_api_key:
            try:
                headers = {
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                }
                data = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You are a professional quantitative sports predictor. Refine the provided logic into a seamless 2-3 sentence AI reasoning paragraph stating why this bet was picked based on short term API form vs long term model pedigree."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.4
                }
                response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=5)
                if response.status_code == 200:
                    return response.json()['choices'][0]['message']['content'].strip()
            except Exception as e:
                logger.error(f"OpenAI API Error in reasoning synthesis: {e}")
                
        if self.gemini_api_key:
             try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"
                data = {
                    "contents": [{
                        "parts":[{"text": f"You are a professional quantitative sports predictor. Refine the provided logic into a seamless 2-3 sentence AI reasoning paragraph stating why this bet was picked based on short term API form vs long term model pedigree.\n\nLogic:\n{prompt}"}]
                    }]
                }
                response = requests.post(url, json=data, timeout=5)
                if response.status_code == 200:
                    return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
             except Exception as e:
                 logger.error(f"Gemini API Error in reasoning synthesis: {e}")

        return ""

    async def generate_reasoning(self, match_context: dict) -> str:
        """
        Takes context dict:
        {
           'home_team': str,
           'away_team': str,
           'pick_label': str,
           'risk_level': str,
           'home_form': float,
           'away_form': float,
           'model_weight': float,
           'category': str
        }
        """
        deterministic_text = self._generate_deterministic_logic(match_context)
        
        if self.openai_api_key or self.gemini_api_key:
            llm_text = self._call_llm_api(deterministic_text)
            if llm_text:
                return llm_text
                
        return deterministic_text
