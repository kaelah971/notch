"""Stable identities, alias resolution, canonical JSON and category inference.

The radar deliberately uses a small, curated alias table. Unknown sources keep a
source-specific identity instead of being merged by fuzzy name similarity.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .models import Category


class AliasConflictError(ValueError):
    """Raised when one alias is claimed by two entities."""


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("_", " ")
    value = re.sub(r"[^\w\s]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    normalized = normalize_name(value)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stable_id(prefix: str, value: str, length: int = 20) -> str:
    return f"{prefix}_{sha256_text(value)[:length]}"


def candidate_id_for(canonical_topic_id: str) -> str:
    return stable_id("cand", canonical_topic_id)


@dataclass(frozen=True)
class EntityDefinition:
    key: str
    category: Category
    wiki_article: str
    aliases: tuple[str, ...]
    coingecko_ids: tuple[str, ...] = ()
    coingecko_symbols: tuple[str, ...] = ()


ENTITIES: tuple[EntityDefinition, ...] = (
    EntityDefinition(
        key="bitcoin",
        category=Category.CRYPTO,
        wiki_article="Bitcoin",
        aliases=("bitcoin", "btc"),
        coingecko_ids=("bitcoin",),
        coingecko_symbols=("btc",),
    ),
    EntityDefinition(
        key="ethereum",
        category=Category.CRYPTO,
        wiki_article="Ethereum",
        aliases=("ethereum", "eth"),
        coingecko_ids=("ethereum",),
        coingecko_symbols=("eth",),
    ),
    EntityDefinition(
        key="solana",
        category=Category.CRYPTO,
        wiki_article="Solana (blockchain platform)",
        aliases=("solana",),
        coingecko_ids=("solana",),
    ),
    EntityDefinition(
        key="dogecoin",
        category=Category.CRYPTO,
        wiki_article="Dogecoin",
        aliases=("dogecoin", "doge"),
        coingecko_ids=("dogecoin",),
        coingecko_symbols=("doge",),
    ),
    EntityDefinition(
        key="zcash",
        category=Category.CRYPTO,
        wiki_article="Zcash",
        aliases=("zcash", "zec"),
        coingecko_ids=("zcash",),
        coingecko_symbols=("zec",),
    ),
    EntityDefinition(
        key="chatgpt",
        category=Category.AI,
        wiki_article="ChatGPT",
        aliases=("chatgpt", "chat gpt"),
    ),
    EntityDefinition(
        key="openai",
        category=Category.AI,
        wiki_article="OpenAI",
        aliases=("openai",),
    ),
    EntityDefinition(
        key="artificial_intelligence",
        category=Category.AI,
        wiki_article="Artificial intelligence",
        aliases=("artificial intelligence",),
    ),
    EntityDefinition(
        key="nvidia",
        category=Category.AI,
        wiki_article="Nvidia",
        aliases=("nvidia", "nvda"),
    ),
)

ENTITY_BY_KEY: dict[str, EntityDefinition] = {entity.key: entity for entity in ENTITIES}
WIKI_TITLE_INDEX: dict[str, str] = {}
ALIAS_INDEX: dict[str, str] = {}
COINGECKO_ID_INDEX: dict[str, str] = {}
COINGECKO_SYMBOL_INDEX: dict[str, str] = {}
_ALIAS_PATTERNS: list[tuple[str, str]] = []

for _entity in ENTITIES:
    _normalized_wiki = normalize_name(_entity.wiki_article)
    existing = WIKI_TITLE_INDEX.get(_normalized_wiki)
    if existing and existing != _entity.key:
        raise AliasConflictError(
            f"wiki title alias conflict: {_entity.wiki_article!r} -> {existing} / {_entity.key}"
        )
    WIKI_TITLE_INDEX[_normalized_wiki] = _entity.key

    for _alias in _entity.aliases:
        _normalized_alias = normalize_name(_alias)
        existing = ALIAS_INDEX.get(_normalized_alias)
        if existing and existing != _entity.key:
            raise AliasConflictError(
                f"alias conflict: {_alias!r} -> {existing} / {_entity.key}"
            )
        ALIAS_INDEX[_normalized_alias] = _entity.key

    for _coin_id in _entity.coingecko_ids:
        existing = COINGECKO_ID_INDEX.get(_coin_id)
        if existing and existing != _entity.key:
            raise AliasConflictError(
                f"coingecko id conflict: {_coin_id!r} -> {existing} / {_entity.key}"
            )
        COINGECKO_ID_INDEX[_coin_id] = _entity.key

    for _symbol in _entity.coingecko_symbols:
        existing = COINGECKO_SYMBOL_INDEX.get(_symbol.casefold())
        if existing and existing != _entity.key:
            raise AliasConflictError(
                f"coingecko symbol conflict: {_symbol!r} -> {existing} / {_entity.key}"
            )
        COINGECKO_SYMBOL_INDEX[_symbol.casefold()] = _entity.key

for _alias, _key in ALIAS_INDEX.items():
    if re.fullmatch(r"[a-z0-9 ]+", _alias):
        _ALIAS_PATTERNS.append((_alias, _key))
_ALIAS_PATTERNS.sort(key=lambda item: (-len(item[0]), item[0], item[1]))


CATEGORY_KEYWORDS: tuple[tuple[Category, tuple[str, ...]], ...] = (
    (
        Category.CRYPTO,
        (
            "bitcoin",
            "btc",
            "ethereum",
            "eth",
            "crypto",
            "cryptocurrency",
            "blockchain",
            "solana",
            "dogecoin",
            "stablecoin",
            "defi",
            "nft",
            "web3",
            "token",
        ),
    ),
    (
        Category.AI,
        (
            "artificial intelligence",
            "machine learning",
            "chatgpt",
            "openai",
            "open source",
            "software",
            "technology",
            "computer",
            "algorithm",
            "robot",
            "robotics",
            "nvidia",
            "semiconductor",
            "chip",
            "google",
            "microsoft",
            "apple",
            "meta",
            "quantum",
            "cybersecurity",
        ),
    ),
    (
        Category.GAMING,
        (
            "video game",
            "video games",
            "gaming",
            "game",
            "games",
            "esports",
            "film",
            "films",
            "movie",
            "movies",
            "box office",
            "anime",
            "manga",
            "television",
            "tv series",
            "netflix",
            "album",
            "song",
            "music",
            "singer",
            "band",
        ),
    ),
    (
        Category.POP,
        (
            "celebrity",
            "actor",
            "actress",
            "comedian",
            "influencer",
            "youtuber",
            "royal",
            "marriage",
            "divorce",
            "dating",
            "fashion",
            "model",
        ),
    ),
    (
        Category.NEWS,
        (
            "election",
            "elections",
            "president",
            "prime minister",
            "minister",
            "senate",
            "congress",
            "parliament",
            "protest",
            "war",
            "strike",
            "disaster",
            "earthquake",
            "flood",
            "hurricane",
            "storm",
            "court",
            "trial",
            "verdict",
            "death",
            "deaths",
            "died",
            "killed",
            "resign",
            "resignation",
            "policy",
            "immigration",
        ),
    ),
)

_CATEGORY_PATTERNS: dict[Category, list[re.Pattern[str]]] = {}
for _category, _keywords in CATEGORY_KEYWORDS:
    _CATEGORY_PATTERNS[_category] = [
        re.compile(rf"(?<![\w]){re.escape(keyword)}(?![\w])", re.IGNORECASE)
        for keyword in _keywords
    ]


def build_alias_index(definitions: tuple[EntityDefinition, ...] | list[EntityDefinition]) -> dict[str, str]:
    """Build a normalized alias index and reject conflicting claims."""
    index: dict[str, str] = {}
    for entity in definitions:
        for alias in entity.aliases:
            normalized = normalize_name(alias)
            existing = index.get(normalized)
            if existing and existing != entity.key:
                raise AliasConflictError(
                    f"alias conflict: {alias!r} -> {existing} / {entity.key}"
                )
            index[normalized] = entity.key
    return index


def find_entity_in_text(text: str) -> tuple[str, str] | None:
    """Conservative whole-word alias match; longest alias wins."""
    normalized = normalize_name(text)
    for alias, entity_key in _ALIAS_PATTERNS:
        pattern = re.compile(rf"(?<![\w]){re.escape(alias)}(?![\w])")
        if pattern.search(normalized):
            return entity_key, alias
    return None


def entity_for_wiki_article(article: str) -> EntityDefinition | None:
    key = WIKI_TITLE_INDEX.get(normalize_name(article))
    return ENTITY_BY_KEY.get(key) if key else None


def entity_for_coingecko(
    coin_id: str, symbol: str, name: str
) -> EntityDefinition | None:
    key = COINGECKO_ID_INDEX.get(coin_id.casefold())
    if not key:
        key = COINGECKO_SYMBOL_INDEX.get(symbol.casefold())
    if not key:
        key = ALIAS_INDEX.get(normalize_name(name))
    return ENTITY_BY_KEY.get(key) if key else None


def infer_category(text: str, default: Category = Category.OTHER) -> Category:
    normalized = normalize_name(text)
    scores: dict[Category, int] = {}
    for category, patterns in _CATEGORY_PATTERNS.items():
        score = sum(1 for pattern in patterns if pattern.search(normalized))
        if score:
            scores[category] = score
    if not scores:
        return default
    order = {category: index for index, category in enumerate(Category)}
    return sorted(scores.items(), key=lambda item: (-item[1], order[item[0]]))[0][0]


def category_aliases_for(entity: EntityDefinition) -> list[str]:
    return sorted(set(entity.aliases) | {entity.wiki_article, entity.key})
