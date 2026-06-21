---
name: literature-source-finder
description: Find candidate English scholarly sources for communication and journalism studies claims, qualitative findings, literature-review paragraphs, or unsupported academic prose. Use when Codex needs to turn a paragraph into searchable claims, query open literature metadata, classify evidence relationships, and produce a cautious evidence map with source-verification warnings.
---

# Literature Source Finder

Use this skill to find candidate literature for a user-provided claim, qualitative finding, discussion paragraph, or unsupported academic prose in journalism, communication, media studies, and adjacent social-science fields.

The skill is for evidence discovery, not automatic proof. Always describe returned papers as candidate sources until the user or Codex has checked the paper itself.

## Workflow

1. Restate the user's research text in 1 sentence.
2. Extract 1-5 atomic claims. Keep each claim narrow enough that a paper could plausibly support, contextualize, or challenge it.
3. Run `scripts/find_sources.py` with the text or extracted claims. Prefer Markdown output for human review and JSON when the user wants downstream tooling.
4. Read `references/evidence_relation_types.md` before assigning relationship labels.
5. Produce an evidence map with:
   - extracted claims
   - search strategy and key query terms
   - ranked candidate sources
   - relation type for each source
   - brief relevance rationale
   - human verification warnings
   - APA-style reference drafts when metadata is sufficient

## Running The Script

Basic use:

```bash
python scripts/find_sources.py --text input.txt --discipline communication --limit 20 --format markdown
```

Use inline text:

```bash
python scripts/find_sources.py --text "Short-video platforms reshape city identity through everyday affective storytelling." --limit 10
```

Use extracted claims:

```bash
python scripts/find_sources.py --claim "Short-video platforms reshape city branding through everyday narratives." --claim "Affective storytelling strengthens place identity." --limit 20 --format markdown,json
```

Useful options:

- `--from-year 2015 --to-year 2026` to restrict publication years.
- `--source openalex` or `--source semantic-scholar` to use only one provider.
- `--verify-crossref` to verify DOI metadata through Crossref when DOI values are present.
- `--no-network` to preview claim extraction and generated queries without calling APIs.

Optional environment variables:

- `OPENALEX_API_KEY`: OpenAlex key for higher limits.
- `OPENALEX_POLITE_EMAIL`: polite pool email for OpenAlex requests when no API key is configured.
- `S2_API_KEY`: Semantic Scholar API key.

## Source Handling

Prefer OpenAlex for broad discovery. Use Semantic Scholar to enrich metadata, abstracts, URLs, and citation counts. Use Crossref only for DOI-level metadata verification, not semantic discovery.

Deduplicate candidates by DOI first, then normalized title. When duplicate records disagree, keep the record with more complete metadata and preserve the provider list.

## Evidence Boundaries

Use cautious language:

- Say "candidate source", "potentially relevant", "theoretically relevant", or "empirical parallel".
- Do not say a source proves or supports a claim unless the available abstract clearly matches the claim and the user understands that full-text reading is still required.
- Separate direct empirical support from theoretical support.
- Flag weak matches instead of padding the bibliography.
- Never invent citations, DOIs, journal names, authors, or abstracts.

## Output Guidance

For each recommended source, include:

- title, authors, year, venue, DOI or URL
- relation type from `references/evidence_relation_types.md`
- short relevance rationale
- what must be checked before citation
- APA draft when enough metadata exists

If fewer than 5 credible candidates are found, say so plainly and suggest broader search terms rather than manufacturing a complete list.
