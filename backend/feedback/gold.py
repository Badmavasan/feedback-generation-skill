"""Gold corpus loader — serves ground-truth examples for GAG (Ground-truth Annotated Grading)."""
import json
import random
from pathlib import Path
from functools import lru_cache

_CORPUS_PATH = Path(__file__).parent / "gold_corpus.json"


@lru_cache(maxsize=1)
def _load_corpus() -> dict[str, list[str]]:
    with open(_CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_gold_examples(characteristic: str, n: int = 2) -> list[str]:
    """
    Return up to n gold-standard examples for the given characteristic.
    Sampled randomly so the judge sees variety across calls.
    Filters out placeholder/stub entries (length < 15 chars).
    """
    corpus = _load_corpus()
    candidates = [
        ex for ex in corpus.get(characteristic, [])
        if len(ex.strip()) >= 15
    ]
    return random.sample(candidates, min(n, len(candidates)))
