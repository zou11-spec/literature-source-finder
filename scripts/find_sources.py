#!/usr/bin/env python3
"""Find candidate scholarly sources for communication-studies claims.

This script intentionally performs source discovery and metadata ranking only.
It does not certify that a paper supports a claim; full-text reading is still
required before formal citation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


OPENALEX_ENDPOINT = "https://api.openalex.org/works"
SEMANTIC_SCHOLAR_ENDPOINT = "https://api.semanticscholar.org/graph/v1/paper/search"
CROSSREF_WORKS_ENDPOINT = "https://api.crossref.org/works"

COMMUNICATION_TERMS = [
    "communication",
    "journalism",
    "media studies",
    "digital media",
    "social media",
    "platform studies",
]

CONCEPT_MAP = {
    "short video": ["short video", "TikTok", "Douyin", "platform"],
    "短视频": ["short video", "TikTok", "Douyin", "platform"],
    "city": ["city branding", "urban communication", "place identity"],
    "城市": ["city branding", "urban communication", "place identity"],
    "identity": ["identity construction", "place identity", "collective identity"],
    "认同": ["identity construction", "place identity", "collective identity"],
    "emotion": ["affect", "emotion", "affective publics"],
    "情感": ["affect", "emotion", "affective publics"],
    "narrative": ["narrative", "storytelling", "discourse"],
    "叙事": ["narrative", "storytelling", "discourse"],
    "algorithm": ["algorithmic visibility", "algorithmic curation", "platform governance"],
    "算法": ["algorithmic visibility", "algorithmic curation", "platform governance"],
    "crisis": ["crisis communication", "risk communication", "public communication"],
    "危机": ["crisis communication", "risk communication", "public communication"],
    "news": ["news consumption", "journalism", "news media"],
    "新闻": ["news consumption", "journalism", "news media"],
    "framing": ["framing", "media frames", "frame analysis"],
    "框架": ["framing", "media frames", "frame analysis"],
    "public": ["public sphere", "public opinion", "affective publics"],
    "公众": ["public sphere", "public opinion", "affective publics"],
}

THEORY_HINTS = {
    "theory",
    "framework",
    "framing",
    "agenda setting",
    "affordance",
    "platformization",
    "mediatization",
    "identity",
    "public sphere",
    "affective publics",
    "discourse",
    "narrative",
    "city branding",
}

EMPIRICAL_HINTS = {
    "study",
    "analysis",
    "interview",
    "survey",
    "case study",
    "content analysis",
    "ethnography",
    "qualitative",
    "quantitative",
    "findings",
    "data",
}

COUNTERPOINT_HINTS = {
    "contradict",
    "critique",
    "criticize",
    "criticism",
    "against",
    "ambivalent",
}


@dataclass
class Candidate:
    title: str
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    cited_by_count: int = 0
    providers: list[str] = field(default_factory=list)
    provider_ids: list[str] = field(default_factory=list)
    open_access_url: str | None = None
    source_relevance: float = 0.0
    score: float = 0.0
    relation_type: str = "weak_match"
    matched_queries: list[str] = field(default_factory=list)
    metadata_verification: str = "not_verified"
    warnings: list[str] = field(default_factory=list)

    def key(self) -> str:
        if self.doi:
            return f"doi:{normalize_doi(self.doi)}"
        return f"title:{normalize_title(self.title)}"


def normalize_doi(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    return value


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9-]{2,}", value.lower())
        if token not in {"the", "and", "for", "with", "from", "into", "that", "this"}
    }


def read_text_arg(value: str | None) -> str:
    if not value:
        return ""
    path = Path(value)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return value


def extract_claims(text: str, explicit_claims: list[str]) -> list[str]:
    claims = [claim.strip() for claim in explicit_claims if claim.strip()]
    if claims:
        return claims[:5]

    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []

    parts = re.split(r"(?<=[.!?。！？；;])\s*", cleaned)
    parts = [part.strip(" ;；") for part in parts if len(part.strip()) >= 12]
    if not parts:
        parts = [cleaned]
    return parts[:5]


def infer_concepts(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.lower()
    for needle, terms in CONCEPT_MAP.items():
        if needle.lower() in lowered:
            for term in terms:
                if term not in found:
                    found.append(term)
    return found


def build_queries(claims: list[str], discipline: str) -> list[str]:
    queries: list[str] = []
    discipline_terms = COMMUNICATION_TERMS if discipline == "communication" else [discipline]
    all_text = " ".join(claims)
    concepts = infer_concepts(all_text)

    for claim in claims:
        trimmed = claim.strip()
        if trimmed:
            queries.append(trimmed[:350])
            if concepts:
                queries.append(" ".join((concepts + discipline_terms)[:8]))

    if concepts:
        queries.append(" ".join((concepts + discipline_terms)[:10]))
    else:
        queries.append(" ".join(discipline_terms + claims[:1])[:350])

    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = re.sub(r"\s+", " ", query).strip().lower()
        if normalized and normalized not in seen:
            deduped.append(query.strip())
            seen.add(normalized)
    return deduped[:8]


def request_json(url: str, params: dict[str, Any], headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    full_url = f"{url}?{query}" if query else url
    request = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "literature-source-finder/0.1 (+https://github.com/)",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 or exc.code < 500 or attempt == 2:
                raise
            last_error = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 2:
                raise
            last_error = exc
        time.sleep(0.4 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("Request failed without an error.")


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    positions: list[tuple[int, str]] = []
    for word, indexes in index.items():
        for position in indexes:
            positions.append((position, word))
    positions.sort()
    if not positions:
        return None
    return " ".join(word for _, word in positions)


def openalex_auth_params() -> dict[str, str]:
    params: dict[str, str] = {}
    api_key = os.getenv("OPENALEX_API_KEY")
    email = os.getenv("OPENALEX_POLITE_EMAIL")
    if api_key:
        params["api_key"] = api_key
    if email:
        params["mailto"] = email
    return params


def search_openalex(query: str, limit: int, from_year: int | None, to_year: int | None) -> list[Candidate]:
    filters: list[str] = []
    if from_year:
        filters.append(f"from_publication_date:{from_year}-01-01")
    if to_year:
        filters.append(f"to_publication_date:{to_year}-12-31")

    base_params: dict[str, Any] = {
        "per-page": min(max(limit, 1), 100),
        "sort": "relevance_score:desc",
        "select": "id,doi,display_name,title,publication_year,authorships,primary_location,open_access,cited_by_count,relevance_score,abstract_inverted_index",
        **openalex_auth_params(),
    }
    if filters:
        base_params["filter"] = ",".join(filters)

    params = dict(base_params)
    if len(query) > 80:
        params["search.semantic"] = query
    else:
        params["search"] = query

    try:
        data = request_json(OPENALEX_ENDPOINT, params)
    except urllib.error.HTTPError:
        if "search.semantic" not in params:
            raise
        params.pop("search.semantic", None)
        params["search"] = query
        data = request_json(OPENALEX_ENDPOINT, params)

    candidates: list[Candidate] = []
    for item in data.get("results", []):
        title = item.get("display_name") or item.get("title")
        if not title:
            continue

        primary_location = item.get("primary_location") or {}
        source = primary_location.get("source") or {}
        open_access = item.get("open_access") or {}
        authors = []
        for authorship in item.get("authorships", [])[:6]:
            author = authorship.get("author") or {}
            name = author.get("display_name")
            if name:
                authors.append(name)

        candidates.append(
            Candidate(
                title=title,
                year=item.get("publication_year"),
                authors=authors,
                venue=source.get("display_name"),
                doi=normalize_doi(item.get("doi")),
                url=item.get("doi") or item.get("id"),
                abstract=abstract_from_inverted_index(item.get("abstract_inverted_index")),
                cited_by_count=item.get("cited_by_count") or 0,
                providers=["openalex"],
                provider_ids=[item.get("id")] if item.get("id") else [],
                open_access_url=open_access.get("oa_url"),
                source_relevance=float(item.get("relevance_score") or 0.0),
                matched_queries=[query],
            )
        )
    return candidates


def search_semantic_scholar(query: str, limit: int, from_year: int | None, to_year: int | None) -> list[Candidate]:
    year_filter = None
    if from_year and to_year:
        year_filter = f"{from_year}-{to_year}"
    elif from_year:
        year_filter = f"{from_year}-"
    elif to_year:
        year_filter = f"-{to_year}"

    params = {
        "query": query,
        "limit": min(max(limit, 1), 100),
        "fields": "paperId,title,authors,year,venue,url,abstract,citationCount,externalIds,openAccessPdf",
        "year": year_filter,
    }
    headers = {}
    api_key = os.getenv("S2_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    data = request_json(SEMANTIC_SCHOLAR_ENDPOINT, params, headers=headers)
    candidates: list[Candidate] = []
    for item in data.get("data", []):
        title = item.get("title")
        if not title:
            continue
        external_ids = item.get("externalIds") or {}
        doi = normalize_doi(external_ids.get("DOI"))
        authors = [author.get("name") for author in item.get("authors", [])[:6] if author.get("name")]
        open_pdf = item.get("openAccessPdf") or {}
        candidates.append(
            Candidate(
                title=title,
                year=item.get("year"),
                authors=authors,
                venue=item.get("venue"),
                doi=doi,
                url=item.get("url"),
                abstract=item.get("abstract"),
                cited_by_count=item.get("citationCount") or 0,
                providers=["semantic-scholar"],
                provider_ids=[item.get("paperId")] if item.get("paperId") else [],
                open_access_url=open_pdf.get("url"),
                source_relevance=0.0,
                matched_queries=[query],
            )
        )
    return candidates


def merge_candidate(existing: Candidate, incoming: Candidate) -> Candidate:
    for provider in incoming.providers:
        if provider not in existing.providers:
            existing.providers.append(provider)
    for provider_id in incoming.provider_ids:
        if provider_id and provider_id not in existing.provider_ids:
            existing.provider_ids.append(provider_id)
    for query in incoming.matched_queries:
        if query not in existing.matched_queries:
            existing.matched_queries.append(query)

    if not existing.abstract and incoming.abstract:
        existing.abstract = incoming.abstract
    if not existing.doi and incoming.doi:
        existing.doi = incoming.doi
    if not existing.url and incoming.url:
        existing.url = incoming.url
    if not existing.open_access_url and incoming.open_access_url:
        existing.open_access_url = incoming.open_access_url
    if not existing.venue and incoming.venue:
        existing.venue = incoming.venue
    if len(incoming.authors) > len(existing.authors):
        existing.authors = incoming.authors
    existing.cited_by_count = max(existing.cited_by_count, incoming.cited_by_count)
    existing.source_relevance = max(existing.source_relevance, incoming.source_relevance)
    return existing


def dedupe(candidates: Iterable[Candidate]) -> list[Candidate]:
    by_key: dict[str, Candidate] = {}
    title_index: dict[str, str] = {}
    for candidate in candidates:
        if not candidate.title:
            continue
        key = candidate.key()
        title_key = normalize_title(candidate.title)
        if key in by_key:
            merge_candidate(by_key[key], candidate)
        elif title_key in title_index:
            merge_candidate(by_key[title_index[title_key]], candidate)
        else:
            by_key[key] = candidate
            title_index[title_key] = key
    return list(by_key.values())


def classify_relation(candidate: Candidate, claims: list[str]) -> str:
    combined = " ".join([candidate.title, candidate.abstract or ""]).lower()
    claim_tokens = tokenize(" ".join(claims))
    source_tokens = tokenize(combined)
    overlap = len(claim_tokens & source_tokens)

    if any(hint in combined for hint in COUNTERPOINT_HINTS) and overlap >= 3:
        return "counterpoint"
    if overlap < 2:
        return "weak_match"
    if any(hint in combined for hint in THEORY_HINTS):
        return "theoretical_support"
    if any(hint in combined for hint in EMPIRICAL_HINTS):
        return "empirical_parallel"
    if overlap >= 5 and candidate.abstract:
        return "contextual_relevance"
    return "weak_match"


def score_candidate(candidate: Candidate, claims: list[str]) -> float:
    combined = " ".join([candidate.title, candidate.abstract or ""])
    claim_tokens = tokenize(" ".join(claims))
    source_tokens = tokenize(combined)
    overlap = len(claim_tokens & source_tokens)
    overlap_score = min(overlap / max(len(claim_tokens), 1), 1.0)
    citation_score = min(math.log1p(candidate.cited_by_count) / 8.0, 1.0)
    metadata_score = 0.0
    metadata_score += 0.15 if candidate.doi else 0.0
    metadata_score += 0.10 if candidate.abstract else 0.0
    metadata_score += 0.05 if candidate.venue else 0.0
    provider_score = 0.10 if len(candidate.providers) > 1 else 0.0
    openalex_score = min(candidate.source_relevance / 100.0, 0.25)
    return round(overlap_score * 0.45 + citation_score * 0.20 + metadata_score + provider_score + openalex_score, 4)


def verify_crossref(candidates: list[Candidate], max_items: int = 20) -> None:
    checked = 0
    for candidate in candidates:
        if not candidate.doi or checked >= max_items:
            continue
        doi = normalize_doi(candidate.doi)
        try:
            data = request_json(f"{CROSSREF_WORKS_ENDPOINT}/{urllib.parse.quote(doi, safe='')}", {})
            message = data.get("message") or {}
            title = " ".join(message.get("title") or [])
            if title:
                candidate.metadata_verification = "crossref_verified"
            else:
                candidate.metadata_verification = "crossref_record_without_title"
        except Exception as exc:  # noqa: BLE001 - keep CLI resilient across API failures.
            candidate.metadata_verification = "crossref_failed"
            candidate.warnings.append(f"Crossref verification failed: {exc}")
        checked += 1
        time.sleep(0.1)


def make_apa(candidate: Candidate) -> str:
    authors = candidate.authors[:6]
    if not authors:
        author_text = "Unknown author"
    elif len(authors) == 1:
        author_text = authors[0]
    else:
        author_text = ", ".join(authors[:-1]) + f", & {authors[-1]}"
    year = candidate.year or "n.d."
    title = candidate.title.rstrip(".")
    venue = candidate.venue or "Unknown venue"
    doi = f" https://doi.org/{normalize_doi(candidate.doi)}" if candidate.doi else ""
    return f"{author_text} ({year}). {title}. {venue}.{doi}"


def render_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Literature Source Finder Evidence Map")
    lines.append("")
    lines.append("> Candidate sources only. Read the original papers before citing them as support.")
    lines.append("")

    lines.append("## Extracted Claims")
    for i, claim in enumerate(payload["claims"], 1):
        lines.append(f"{i}. {claim}")
    lines.append("")

    lines.append("## Search Strategy")
    for query in payload["queries"]:
        lines.append(f"- {query}")
    if payload["warnings"]:
        lines.append("")
        lines.append("## Warnings")
        for warning in payload["warnings"]:
            lines.append(f"- {warning}")
    lines.append("")

    lines.append("## Candidate Sources")
    if not payload["candidates"]:
        lines.append("No candidates were found. Broaden the wording, add English concepts, or remove year/source filters.")
        return "\n".join(lines) + "\n"

    for i, candidate in enumerate(payload["candidates"], 1):
        doi = candidate.get("doi")
        url = candidate.get("url") or (f"https://doi.org/{doi}" if doi else "")
        lines.append(f"### {i}. {candidate['title']}")
        lines.append(f"- Authors: {', '.join(candidate['authors']) if candidate['authors'] else 'Unknown'}")
        lines.append(f"- Year / venue: {candidate.get('year') or 'n.d.'} / {candidate.get('venue') or 'Unknown venue'}")
        lines.append(f"- Relation type: `{candidate['relation_type']}`")
        lines.append(f"- Relevance score: {candidate['relevance_score']}")
        lines.append(f"- Providers: {', '.join(candidate['providers'])}")
        if doi:
            lines.append(f"- DOI: {doi}")
        if url:
            lines.append(f"- URL: {url}")
        if candidate.get("open_access_url"):
            lines.append(f"- Open access: {candidate['open_access_url']}")
        lines.append(f"- Metadata verification: {candidate['metadata_verification']}")
        lines.append(f"- Why relevant: {candidate['rationale']}")
        lines.append(f"- Check before citing: {candidate['verification_note']}")
        lines.append(f"- APA draft: {candidate['apa_draft']}")
        if candidate.get("warnings"):
            lines.append(f"- Warnings: {'; '.join(candidate['warnings'])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def candidate_to_dict(candidate: Candidate, claims: list[str]) -> dict[str, Any]:
    rationale = relation_rationale(candidate)
    verification_note = "Read the abstract and full text to confirm the source actually supports the target claim."
    if candidate.relation_type in {"weak_match", "contextual_relevance"}:
        verification_note = "Treat as background only unless full-text reading shows a closer relationship."
    if candidate.relation_type == "counterpoint":
        verification_note = "Check whether this source qualifies or contradicts the claim; do not cite it as support without nuance."

    return {
        "title": candidate.title,
        "authors": candidate.authors,
        "year": candidate.year,
        "venue": candidate.venue,
        "doi": normalize_doi(candidate.doi),
        "url": candidate.url,
        "open_access_url": candidate.open_access_url,
        "providers": candidate.providers,
        "provider_ids": candidate.provider_ids,
        "relation_type": candidate.relation_type,
        "relevance_score": candidate.score,
        "metadata_verification": candidate.metadata_verification,
        "matched_queries": candidate.matched_queries,
        "rationale": rationale,
        "verification_note": verification_note,
        "apa_draft": make_apa(candidate),
        "warnings": candidate.warnings,
    }


def relation_rationale(candidate: Candidate) -> str:
    title = candidate.title
    if candidate.relation_type == "theoretical_support":
        return f"The title/abstract suggests a theoretical or conceptual connection to the claim: {title}."
    if candidate.relation_type == "empirical_parallel":
        return f"The source appears to study a related communication/media phenomenon and may offer an empirical parallel: {title}."
    if candidate.relation_type == "counterpoint":
        return f"The source may complicate or qualify the claim and should be reviewed as possible counter-evidence: {title}."
    if candidate.relation_type == "contextual_relevance":
        return f"The source shares important context or terminology with the claim but is not yet confirmed as support: {title}."
    return f"The source matched broad search terms, but available metadata is too limited for a stronger relationship label: {title}."


def run(args: argparse.Namespace) -> dict[str, Any]:
    text = read_text_arg(args.text)
    claims = extract_claims(text, args.claim)
    queries = build_queries(claims, args.discipline)
    warnings: list[str] = []

    if not claims:
        warnings.append("No usable claim text was provided.")

    if args.no_network:
        return {"claims": claims, "queries": queries, "candidates": [], "warnings": warnings}

    raw_candidates: list[Candidate] = []
    providers = set(args.source)
    per_query_limit = max(args.limit, 5)

    for query in queries:
        if "openalex" in providers:
            try:
                raw_candidates.extend(search_openalex(query, per_query_limit, args.from_year, args.to_year))
            except Exception as exc:  # noqa: BLE001 - discovery should degrade gracefully.
                warnings.append(f"OpenAlex search failed for query {query!r}: {exc}")
        if "semantic-scholar" in providers:
            try:
                raw_candidates.extend(search_semantic_scholar(query, per_query_limit, args.from_year, args.to_year))
            except Exception as exc:  # noqa: BLE001 - discovery should degrade gracefully.
                warnings.append(f"Semantic Scholar search failed for query {query!r}: {exc}")

    candidates = dedupe(raw_candidates)
    for candidate in candidates:
        candidate.relation_type = classify_relation(candidate, claims)
        candidate.score = score_candidate(candidate, claims)

    candidates.sort(key=lambda item: item.score, reverse=True)
    candidates = candidates[: args.limit]

    if args.verify_crossref:
        verify_crossref(candidates)

    if not candidates:
        warnings.append("No candidate sources found after API search and deduplication.")
    elif all(candidate.relation_type == "weak_match" for candidate in candidates[: min(5, len(candidates))]):
        warnings.append("Top candidates are weak matches; broaden or translate the claim into more specific English concepts.")

    return {
        "claims": claims,
        "queries": queries,
        "candidates": [candidate_to_dict(candidate, claims) for candidate in candidates],
        "warnings": warnings,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find candidate literature sources for communication-studies claims.")
    parser.add_argument("--text", help="Inline text or path to a UTF-8 text file.")
    parser.add_argument("--claim", action="append", default=[], help="Atomic claim. Repeat up to five times.")
    parser.add_argument("--discipline", default="communication", help="Discipline hint. Default: communication.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of candidates to return.")
    parser.add_argument("--from-year", type=int, help="Earliest publication year.")
    parser.add_argument("--to-year", type=int, help="Latest publication year.")
    parser.add_argument(
        "--source",
        action="append",
        choices=["openalex", "semantic-scholar"],
        help="Source provider to query. Repeat to use both. Default: both.",
    )
    parser.add_argument(
        "--format",
        default="markdown",
        help="Output format: markdown, json, or markdown,json. Default: markdown.",
    )
    parser.add_argument("--verify-crossref", action="store_true", help="Verify DOI metadata through Crossref.")
    parser.add_argument("--no-network", action="store_true", help="Preview claims and generated queries without API calls.")
    args = parser.parse_args(argv)
    if not args.source:
        args.source = ["openalex", "semantic-scholar"]
    args.limit = max(1, min(args.limit, 100))
    return args


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv or sys.argv[1:])
    payload = run(args)
    formats = {item.strip().lower() for item in args.format.split(",") if item.strip()}

    if "markdown" in formats:
        sys.stdout.write(render_markdown(payload))
    if "json" in formats:
        if "markdown" in formats:
            sys.stdout.write("\n```json\n")
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
        if "markdown" in formats:
            sys.stdout.write("```\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
