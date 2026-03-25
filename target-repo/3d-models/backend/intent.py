import os
import json
import google.generativeai as genai

class IntentAnalyzer:
    def __init__(self):
        # Configure Gemini API if key is available
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-1.5-flash")
        else:
            self.model = None

    def parse(self, query: str) -> dict:
        """
        Takes a natural language query and breaks it down into intent using LLM.
        """
        if self.model:
            prompt = f"""
            Analyze the following query to extract structural intent for a 3D model generator.
            Return ONLY a valid JSON object with these keys:
            - primary_keywords (list of strings)
            - structural_components (list of strings representing 3D shapes or distinct parts)
            - context (string, e.g., 'Medical', 'Educational', 'Gaming')

            Query: "{query}"
            """
            try:
                response = self.model.generate_content(prompt)
                text = response.text.strip()
                # Remove markdown formatting if present
                if text.startswith("```json"):
                    text = text[7:-3]
                elif text.startswith("```"):
                    text = text[3:-3]
                return json.loads(text.strip())
            except Exception as e:
                print(f"Error accessing Gemini: {e}")
                # Fallback to naive parsing
                return self._naive_parse(query)
        else:
            print("Gemini API key not found. Using naive intent parsing.")
            return self._naive_parse(query)

    def _naive_parse(self, query: str) -> dict:
        """
        A fallback rule-based parser when no LLM is configured.
        """
        words = query.lower().split()
        return {
            "primary_keywords": words,
            "structural_components": words,
            "context": "General"
        }
