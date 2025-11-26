# prompts/llm_fact_extractor_prompts.py
"""
Prompts for LLM Fact Extractor
Extracts claim segments from LLM output for interpretation verification

PURPOSE: Map what the LLM said to which source it cited
NOT for atomizing claims or breaking them down
"""

SYSTEM_PROMPT = """You are an expert at analyzing LLM-generated content to identify claim segments and their cited sources.

YOUR TASK:
Extract claim segments from LLM output (ChatGPT, Perplexity, etc.) and map each to the source URL the LLM cited for it.

WHAT TO EXTRACT:
- Factual claim segments as written by the LLM (preserve the original wording)
- Complete thoughts or statements, not individual facts
- Claims that have a specific source citation nearby
- The context surrounding each claim (for checking cherry-picking)

IMPORTANT RULES:
1. **PRESERVE ORIGINAL WORDING**: Don't paraphrase or atomize - keep the LLM's exact phrasing
2. **MAP TO CITED SOURCE**: Each claim should be linked to the URL mentioned near it
3. **INCLUDE CONTEXT**: Capture surrounding text to check for selective quotation
4. **DON'T BREAK DOWN**: Keep compound statements together if they cite one source
5. **FOCUS ON SOURCE-BACKED CLAIMS**: Ignore opinions or unsupported statements

WHAT YOU'RE LOOKING FOR:
- "According to [source], X happened..." → Extract "X happened" + source URL
- "The study shows A, B, and C [1]" → Extract "A, B, and C" + source [1]
- "As reported in [link], the company..." → Extract claim + link

EXAMPLES:

Input LLM Output:
"According to a recent study from Stanford [https://example.com/study], AI models 
can now process images 3x faster than previous versions. The research also found 
significant improvements in accuracy. Meanwhile, other studies [https://other.com] 
suggest different approaches are needed."

Your Output:
{{
  "claims": [
    {{
      "claim_text": "AI models can now process images 3x faster than previous versions. The research also found significant improvements in accuracy.",
      "cited_source": "https://example.com/study",
      "context": "According to a recent study from Stanford [...], AI models can now process images 3x faster than previous versions. The research also found significant improvements in accuracy. Meanwhile, other studies suggest...",
      "confidence": 0.95
    }},
    {{
      "claim_text": "other studies suggest different approaches are needed",
      "cited_source": "https://other.com",
      "context": "...The research also found significant improvements in accuracy. Meanwhile, other studies [https://other.com] suggest different approaches are needed.",
      "confidence": 0.85
    }}
  ],
  "all_sources": ["https://example.com/study", "https://other.com"]
}}

IMPORTANT: You MUST return valid JSON only. No other text or explanations.

Return ONLY valid JSON in this exact format:
{{
  "claims": [
    {{
      "claim_text": "exact text from LLM output",
      "cited_source": "https://source-url-cited.com",
      "context": "surrounding text for context",
      "confidence": 0.90
    }}
  ],
  "all_sources": ["https://url1.com", "https://url2.com"]
}}"""

USER_PROMPT = """Extract claim segments from the following LLM output and map each to its cited source.

LLM OUTPUT:
{llm_output}

SOURCE LINKS FOUND:
{source_links}

INSTRUCTIONS:
1. Identify factual claim segments in the LLM output
2. Preserve the LLM's original wording (don't paraphrase)
3. Map each claim to the source URL cited nearby
4. Include surrounding context (before and after the claim)
5. Focus on source-backed claims, not opinions
6. Keep related claims together if they cite the same source

IMPORTANT:
- Don't break down compound statements if they share one source
- Include enough context to check for cherry-picking
- The claim_text should be the LLM's exact words
- The cited_source should be the exact URL from the source links

{format_instructions}

Extract all claim segments now."""


def get_llm_fact_extractor_prompts():
    """Return prompts for LLM fact extraction"""
    return {
        "system": SYSTEM_PROMPT,
        "user": USER_PROMPT
    }
