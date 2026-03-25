import wikipedia

def get_wikipedia_summary(concept: str, max_sentences: int = 3) -> str:
    """Fetches a short 'AI Overview' from Wikipedia."""
    try:
        # Search for the best matching page title
        search_results = wikipedia.search(concept)
        if not search_results:
            return ""
            
        # Get the summary of the top result
        summary = wikipedia.summary(search_results[0], sentences=max_sentences, auto_suggest=False)
        return summary
    except wikipedia.exceptions.DisambiguationError as e:
        # If ambiguous, just pick the first option and try again
        try:
            return wikipedia.summary(e.options[0], sentences=max_sentences, auto_suggest=False)
        except:
            return ""
    except Exception as e:
        print(f"Wikipedia fetch error: {e}")
        return ""
