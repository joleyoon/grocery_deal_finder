from __future__ import annotations

import re
from typing import Iterable


_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_GROCERY_UNIT_PATTERN = (
    r"(?:\d+(?:\.\d+)?\s*)?(?:lb|lbs|oz|ounce|ounces|each|ea|count|ct|pk|pack|"
    r"fl\s*oz|fluid\s*ounce|fluid\s*ounces|pt|qt|gal|g|kg)"
)
_PRICE_PHRASE_PATTERNS = (
    re.compile(r"about\s*\$\d+(?:\.\d{1,2})?\s*(?:each|ea)", re.IGNORECASE),
    re.compile(r"\$\d+(?:\.\d{1,2})?\s*(?:each|ea)", re.IGNORECASE),
    re.compile(r"\$\d+(?:\.\d{1,2})?(?![\d./])(?!(?:\s*/))", re.IGNORECASE),
    re.compile(
        rf"\$\d+(?:\.\d{{1,2}})?\s*/\s*{_GROCERY_UNIT_PATTERN}",
        re.IGNORECASE,
    ),
)
_UNIT_PRICE_RE = re.compile(
    rf"\$\d+(?:\.\d{{1,2}})?\s*/\s*{_GROCERY_UNIT_PATTERN}",
    re.IGNORECASE,
)
_PRICE_VALUE_RE = re.compile(r"\$(\d+(?:\.\d{1,2})?)")
_DISCOUNT_PREFIXES = ("was ", "discounted from", "save ")


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def keyword_tokens(keyword: str) -> list[str]:
    return _TOKEN_RE.findall(keyword.lower())


def canonical_token(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 4 and (
        token.endswith(("ches", "shes"))
        or token[-3] in {"s", "x", "z"}
    ):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def title_matches_keyword(title: str, keyword: str) -> bool:
    title_tokens = {canonical_token(token) for token in keyword_tokens(title)}
    required_tokens = [canonical_token(token) for token in keyword_tokens(keyword)]
    return bool(required_tokens) and all(token in title_tokens for token in required_tokens)


def extract_price_phrase(text: str) -> str | None:
    cleaned = normalize_whitespace(text)
    for pattern in _PRICE_PHRASE_PATTERNS:
        for match in pattern.finditer(cleaned):
            prefix = cleaned[max(0, match.start() - 24) : match.start()].lower()
            if any(marker in prefix for marker in _DISCOUNT_PREFIXES):
                continue
            return normalize_whitespace(match.group(0))
    return None


def extract_unit_price(text: str) -> str | None:
    cleaned = normalize_whitespace(text)
    match = _UNIT_PRICE_RE.search(cleaned)
    if not match:
        return None
    return normalize_whitespace(match.group(0))


def parse_price_value(price_phrase: str | None) -> float | None:
    if not price_phrase:
        return None
    match = _PRICE_VALUE_RE.search(price_phrase)
    if not match:
        return None
    return float(match.group(1))


def text_after_title(page_text: str, title: str, window: int = 900) -> str:
    cleaned_page = normalize_whitespace(page_text)
    cleaned_title = normalize_whitespace(title)
    if not cleaned_title:
        return cleaned_page[:window]
    index = cleaned_page.lower().find(cleaned_title.lower())
    if index < 0:
        return cleaned_page[:window]
    return cleaned_page[index : index + window]


def unique_in_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return unique_values
