"""Normalize source observations and conservatively deduplicate candidates."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable

from .canonical import (
    ENTITY_BY_KEY,
    candidate_id_for,
    category_aliases_for,
    entity_for_coingecko,
    entity_for_wiki_article,
    find_entity_in_text,
    infer_category,
    normalize_name,
    slugify,
)
from .models import (
    CANDIDATE_SCHEMA,
    Candidate,
    Category,
    EligibilityStatus,
    RawObservation,
    SourceResult,
    jsonable,
)


SOURCE_ORDER = {"wikimedia": 0, "coingecko": 1, "hackernews": 2}


def _classify_observation(observation: RawObservation) -> dict[str, Any]:
    """Return canonical identity metadata for one source observation."""
    if observation.source == "wikimedia":
        entity = entity_for_wiki_article(observation.title)
        if entity:
            return {
                "canonical_topic_id": f"entity:{entity.key}",
                "entity": entity,
                "category": entity.category,
                "settlement_article": entity.wiki_article,
                "settlement_source": "curated_wiki_mapping",
                "aliases": category_aliases_for(entity),
                "ambiguous": False,
            }
        return {
            "canonical_topic_id": f"wiki:en.wikipedia.org:{slugify(observation.title)}",
            "entity": None,
            "category": infer_category(observation.title, Category.OTHER),
            "settlement_article": observation.title,
            "settlement_source": "observed_wiki_article",
            "aliases": [observation.title],
            "ambiguous": False,
        }

    if observation.source == "coingecko":
        identity = observation.source_identity
        entity = entity_for_coingecko(
            str(identity.get("coin_id", "")),
            str(identity.get("symbol", "")),
            str(identity.get("name", observation.title)),
        )
        if entity:
            return {
                "canonical_topic_id": f"entity:{entity.key}",
                "entity": entity,
                "category": entity.category,
                "settlement_article": entity.wiki_article,
                "settlement_source": "curated_wiki_mapping",
                "aliases": category_aliases_for(entity),
                "ambiguous": False,
            }
        return {
            "canonical_topic_id": f"coingecko:coin:{identity.get('coin_id') or slugify(observation.title)}",
            "entity": None,
            "category": Category.CRYPTO,
            "settlement_article": None,
            "settlement_source": None,
            "aliases": [
                observation.title,
                str(identity.get("symbol", "")),
                str(identity.get("coin_id", "")),
            ],
            "ambiguous": False,
        }

    if observation.source == "hackernews":
        match = find_entity_in_text(observation.title)
        if match:
            entity = ENTITY_BY_KEY[match[0]]
            return {
                "canonical_topic_id": f"entity:{entity.key}",
                "entity": entity,
                "category": entity.category,
                "settlement_article": entity.wiki_article,
                "settlement_source": "curated_wiki_mapping",
                "aliases": category_aliases_for(entity),
                "ambiguous": False,
            }
        return {
            "canonical_topic_id": f"hn:topic:{slugify(observation.title)}",
            "entity": None,
            "category": infer_category(observation.title, Category.AI),
            "settlement_article": None,
            "settlement_source": None,
            "aliases": [observation.title],
            "ambiguous": len(normalize_name(observation.title).split()) <= 2,
        }

    return {
        "canonical_topic_id": f"unknown:{slugify(observation.title)}",
        "entity": None,
        "category": Category.OTHER,
        "settlement_article": None,
        "settlement_source": None,
        "aliases": [observation.title],
        "ambiguous": True,
    }


def _merge_aliases(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        key = normalize_name(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _add_source_identity(
    identities: list[dict[str, Any]], observation: RawObservation
) -> None:
    identity = dict(observation.source_identity)
    identity.setdefault("source", observation.source)
    identity.setdefault("source_id", observation.source_id)
    identity.setdefault("title", observation.title)
    identity.setdefault("url", observation.url)
    identity["observed_at"] = observation.observed_at.isoformat().replace(
        "+00:00", "Z"
    )
    identity["reporting_date"] = (
        observation.reporting_date.isoformat()
        if observation.reporting_date
        else None
    )
    identities.append(identity)


def build_candidates(
    source_results: Iterable[SourceResult],
    *,
    now: datetime,
    previous_first_seen: dict[str, datetime] | None = None,
) -> list[Candidate]:
    previous_first_seen = previous_first_seen or {}
    observations: list[RawObservation] = []
    for result in source_results:
        observations.extend(result.observations)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations:
        classified = _classify_observation(observation)
        classified["observation"] = observation
        groups[classified["canonical_topic_id"]].append(classified)

    candidates: list[Candidate] = []
    for canonical_topic_id, entries in groups.items():
        entries.sort(
            key=lambda entry: (
                SOURCE_ORDER.get(entry["observation"].source, 99),
                entry["observation"].source_id,
            )
        )
        entity = next((entry["entity"] for entry in entries if entry["entity"]), None)
        wiki_entries = [
            entry for entry in entries if entry["observation"].source == "wikimedia"
        ]
        title = (
            entity.wiki_article
            if entity
            else (wiki_entries[0]["observation"].title if wiki_entries else entries[0]["observation"].title)
        )
        category = (
            entity.category
            if entity
            else (wiki_entries[0]["category"] if wiki_entries else entries[0]["category"])
        )
        settlement_article = (
            entity.wiki_article
            if entity
            else (wiki_entries[0]["observation"].title if wiki_entries else None)
        )
        settlement_source = (
            "curated_wiki_mapping"
            if entity
            else ("observed_wiki_article" if wiki_entries else None)
        )
        page_id = None
        for entry in wiki_entries:
            identity = entry["observation"].source_identity
            if identity.get("page_id") is not None:
                page_id = identity.get("page_id")
                break

        aliases = _merge_aliases(
            alias for entry in entries for alias in entry["aliases"]
        )
        aliases = _merge_aliases(
            aliases
            + [
                entry["observation"].title
                for entry in entries
            ]
            + [
                str(entry["observation"].source_identity.get("symbol", ""))
                for entry in entries
                if entry["observation"].source_identity.get("symbol")
            ]
        )
        identities: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        urls: list[str] = []
        for entry in entries:
            observation = entry["observation"]
            _add_source_identity(identities, observation)
            evidence.append(jsonable(observation))
            if observation.url and observation.url not in urls:
                urls.append(observation.url)

        newest = max(entry["observation"].observed_at for entry in entries)
        first_seen = previous_first_seen.get(canonical_topic_id, now)
        candidate = Candidate(
            schema_version=CANDIDATE_SCHEMA,
            candidate_id=candidate_id_for(canonical_topic_id),
            canonical_topic_id=canonical_topic_id,
            title=title,
            category=category,
            aliases=aliases,
            source_identities=identities,
            discovery_evidence=evidence,
            source_urls=urls,
            first_seen_at=first_seen,
            last_seen_at=now,
            observed_at=newest,
            discovery_signals={
                "source_count": len({entry["observation"].source for entry in entries}),
                "sources": sorted(
                    {entry["observation"].source for entry in entries},
                    key=lambda source: SOURCE_ORDER.get(source, 99),
                ),
                "settlement_source": settlement_source,
                "settlement_article": settlement_article,
                "settlement_page_id": page_id,
                "measurement_signature": (
                    {
                        "source": "wikimedia-pageviews-v1",
                        "project": "en.wikipedia.org",
                        "access": "all-access",
                        "agent": "user",
                        "metric": "daily_pageviews",
                    }
                    if settlement_article
                    else None
                ),
                "ambiguous": any(entry["ambiguous"] for entry in entries),
            },
            eligibility_status=EligibilityStatus.NEEDS_REVIEW,
            eligibility_reasons=[],
            confidence=0,
            reliability="low",
            proposed_market_modes=[],
            notes=[],
        )
        if not entity and not wiki_entries:
            candidate.notes.append(
                "Source-specific topic with no curated Wikimedia article mapping."
            )
        if entity:
            candidate.notes.append(
                f"Merged by curated entity alias '{entity.key}'."
            )
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.candidate_id)
    return candidates
