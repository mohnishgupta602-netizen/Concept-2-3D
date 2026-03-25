import wikipedia
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

def _fetch_wikipedia_summary(concept: str, max_sentences: int = 3) -> str:
    """Blocking wikipedia fetch logic extracted for timeout wrapping."""
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


def get_wikipedia_summary(concept: str, max_sentences: int = 3, timeout_seconds: int = 6) -> str:
    """Fetch a short Wikipedia overview with a hard timeout to avoid API hangs."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_fetch_wikipedia_summary, concept, max_sentences)
        return future.result(timeout=max(1, int(timeout_seconds)))
    except FutureTimeout:
        print(f"Wikipedia fetch timed out after {timeout_seconds}s for concept: {concept}")
        return ""
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
