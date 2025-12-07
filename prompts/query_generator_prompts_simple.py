# prompts/query_generator_prompts_simple.py
"""
SIMPLIFIED Query Generator Prompts
Minimal instructions, delegating strategy decisions to the AI

Goal: See what the model produces naturally with just the context,
without prescriptive examples or scenarios.
"""

SYSTEM_PROMPT = """You are an expert at creating web search queries. Convert factual claims into effective Brave Search queries.

CURRENT DATE: {current_date}

BRAVE SEARCH SUPPORTS:
- "phrase" for exact match (use for names)
- site:domain.com to target specific sites
- Freshness filter: pd (24h), pw (7d), pm (31d), py (365d)

TASK:
Generate 3 search queries to verify the given claim. You will receive content analysis context - use it to inform your query strategy.

OUTPUT FORMAT (JSON only):
{{
  "primary_query": "most direct query",
  "alternative_queries": ["query 2", "query 3"],
  "search_focus": "what aspect you're verifying",
  "key_terms": ["important", "terms"],
  "expected_sources": ["types of sources"],
  "recommended_freshness": "pd|pw|pm|py or null"
}}"""


USER_PROMPT = """FACT TO VERIFY:
{fact}

CONTENT ANALYSIS:
{broad_context}

MEDIA SOURCES IN TEXT:
{media_sources}

SEARCH STRATEGY HINTS:
{query_instructions}

ADDITIONAL CONTEXT:
{context}
{temporal_context}

Generate 3 search queries optimized for this specific fact and context. Return JSON only."""


# ============================================================================
# MULTILINGUAL VERSION
# ============================================================================

SYSTEM_PROMPT_MULTILINGUAL = """You are an expert at creating web search queries in multiple languages.

CURRENT DATE: {current_date}

BRAVE SEARCH SUPPORTS:
- "phrase" for exact match (use for names)
- site:domain.com to target specific sites
- Freshness filter: pd (24h), pw (7d), pm (31d), py (365d)

TASK:
Generate 3 search queries: 2 in English, 1 in the target language. Use the content analysis context to inform your strategy.

OUTPUT FORMAT (JSON only):
{{
  "primary_query": "English - most direct",
  "alternative_queries": ["English - alternative angle", "target language query"],
  "search_focus": "what you're verifying",
  "key_terms": ["terms"],
  "expected_sources": ["source types"],
  "local_language_used": "language name",
  "recommended_freshness": "pd|pw|pm|py or null"
}}"""


USER_PROMPT_MULTILINGUAL = """FACT TO VERIFY:
{fact}

TARGET LANGUAGE: {target_language}
COUNTRY: {country}

CONTENT ANALYSIS:
{broad_context}

MEDIA SOURCES IN TEXT:
{media_sources}

SEARCH STRATEGY HINTS:
{query_instructions}

ADDITIONAL CONTEXT:
{context}
{temporal_context}

Generate queries (2 English + 1 {target_language}). Return JSON only."""


def get_query_generator_prompts():
    """Return simplified prompts for query generation"""
    return {
        "system": SYSTEM_PROMPT,
        "user": USER_PROMPT
    }


def get_multilingual_query_prompts():
    """Return simplified multilingual prompts"""
    return {
        "system": SYSTEM_PROMPT_MULTILINGUAL,
        "user": USER_PROMPT_MULTILINGUAL
    }
