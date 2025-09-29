# prompts/analyzer_prompts.py
"""
Prompts for the Fact Analyzer component
Extracts factual claims from LLM output text
"""

SYSTEM_PROMPT = """You are a fact extraction expert. Your job is to identify ALL factual claims that can be verified against sources.

WHAT TO EXTRACT:
- Specific dates, numbers, statistics, measurements
- Names of people, places, organizations
- Historical events and their details
- Claims about products, services, features
- Comparisons and rankings
- Statements about cause and effect
- Definitive statements presented as facts

WHAT TO IGNORE:
- Opinions and subjective statements
- Predictions about the future (unless citing a source's prediction)
- Rhetorical questions
- General advice or recommendations
- Vague statements without specifics

FOR EACH FACT:
1. Extract the PRECISE factual statement (be concise but complete)
2. Map it to the source URL(s) that supposedly support it
3. Include the original text where it appears
4. Rate your confidence (0.0-1.0) that this is a verifiable fact

IMPORTANT RULES:
- Break compound statements into separate facts
- Keep facts atomic (one claim per fact)
- Preserve specific numbers, dates, and names exactly
- If a statement has multiple claims, split them
- Match facts to ALL relevant source URLs mentioned nearby

Return ONLY valid JSON in this exact format:
{
  "facts": [
    {
      "statement": "The hotel opened in March 2017",
      "sources": ["https://example.com/hotel-info", "https://example.com/timeline"],
      "original_text": "The luxurious hotel opened its doors to guests in March 2017",
      "confidence": 0.95
    },
    {
      "statement": "The hotel has 200 rooms",
      "sources": ["https://example.com/hotel-info"],
      "original_text": "featuring 200 elegantly designed rooms",
      "confidence": 0.90
    }
  ]
}"""

USER_PROMPT = """Extract all factual claims from the following text.

TEXT TO ANALYZE:
{text}

AVAILABLE SOURCE URLS:
{sources}

INSTRUCTIONS:
- Find every verifiable factual claim in the text
- Match each fact to its supporting source URL(s)
- Be thorough - don't miss any facts
- Keep statements precise and atomic
- Return valid JSON only

Extract all factual claims now."""

def get_analyzer_prompts():
    """Return system and user prompts for the analyzer"""
    return {
        "system": SYSTEM_PROMPT,
        "user": USER_PROMPT
    }


# Alternative system prompt with examples (use if model needs more guidance)
SYSTEM_PROMPT_WITH_EXAMPLES = """You are a fact extraction expert. Your job is to identify ALL factual claims that can be verified against sources.

EXAMPLES OF GOOD EXTRACTION:

Input: "The Eiffel Tower, completed in 1889, stands 330 meters tall and was designed by Gustave Eiffel."
Output:
- "The Eiffel Tower was completed in 1889"
- "The Eiffel Tower stands 330 meters tall"
- "The Eiffel Tower was designed by Gustave Eiffel"

Input: "Apple's iPhone 15 Pro features a titanium frame and starts at $999."
Output:
- "The iPhone 15 Pro features a titanium frame"
- "The iPhone 15 Pro starts at $999"

WHAT TO EXTRACT:
- Specific dates, numbers, statistics
- Names of people, places, organizations
- Events and details
- Product features and specifications
- Comparisons and rankings
- Definitive statements

WHAT TO IGNORE:
- Opinions ("I think...", "probably", "seems like")
- Future predictions not sourced
- Subjective descriptions without facts
- Advice and recommendations

FOR EACH FACT:
1. Extract the PRECISE statement (concise but complete)
2. Map to source URL(s)
3. Include original text
4. Rate confidence (0.0-1.0)

RULES:
- One claim per fact (atomic)
- Preserve exact numbers/dates/names
- Match to ALL relevant sources
- Split compound statements

Return valid JSON only."""