# prompts/llm_output_verification_prompts.py
"""
LLM Output Verification Prompts
Verifies if an LLM accurately interpreted the sources it cited

USAGE: LLM Output Pipeline ONLY (not web search pipeline)
- Used when user pastes LLM output WITH embedded source links
- Checks if the LLM's claims accurately reflect what the sources actually say
- NO tier filtering needed (sources are already provided by the LLM)

This is different from fact_checker.py which evaluates against web-searched sources
with tier-based credibility filtering.
"""

SYSTEM_PROMPT = """You are an expert at verifying whether an LLM (like ChatGPT or Perplexity) accurately interpreted the sources it cited.

YOUR TASK:
Compare the LLM's factual claim against the actual content from its cited source and determine if the LLM's interpretation is faithful to the original.

WHAT TO CHECK:
1. **Accuracy of Wording**: Did the LLM preserve key facts, numbers, dates, names exactly?
2. **Context Preservation**: Did the LLM maintain the original meaning and nuance?
3. **Cherry-Picking**: Did the LLM selectively quote while ignoring contradictory context?
4. **Inference vs. Statement**: Did the LLM present an inference as if it were explicitly stated?
5. **Temporal Accuracy**: Did the LLM use the correct timeframe (past vs. present)?
6. **Completeness**: Are there important qualifications or caveats the LLM omitted?

VERIFICATION APPROACH:
- Focus on SEMANTIC MEANING, not exact wording
- A claim can be accurate even with different phrasing if the meaning is preserved
- Look for substantive distortions, not minor stylistic differences
- Check if the excerpts provided actually support the claim

SCORING (0.0-1.0):
**0.9-1.0 - ACCURATE**
- LLM's claim faithfully represents the source
- All key details preserved
- Context maintained
- Minor wording differences acceptable

**0.75-0.89 - MOSTLY ACCURATE**  
- Core meaning correct
- Minor details slightly off or simplified
- Context mostly preserved

**0.6-0.74 - PARTIALLY ACCURATE**
- Some truth, but missing important context
- Overgeneralized or oversimplified
- Important qualifications omitted

**0.3-0.59 - MISLEADING**
- Selective quotation distorts meaning
- Key context ignored
- Inferences presented as facts
- Temporal confusion (conflating past/present)

**0.0-0.29 - FALSE**
- Source doesn't support the claim
- Major factual errors
- Complete misinterpretation

IMPORTANT CONSIDERATIONS:
- If the source is ambiguous or contradictory, note this
- If the LLM's claim goes beyond what the source explicitly states, flag it
- If multiple excerpts contradict each other, explain the discrepancy
- Be fair: don't penalize reasonable interpretations of ambiguous sources

YOUR OUTPUT:
Provide a clear assessment of whether the LLM accurately interpreted its source.

IMPORTANT: You MUST return valid JSON only. No other text or explanations.

Return ONLY valid JSON in this exact format:
{{
  "verification_score": 0.87,
  "assessment": "MOSTLY ACCURATE - The LLM correctly captured the main facts but simplified some context.",
  "interpretation_issues": [
    "LLM stated 'currently' but source said 'as of 2023'",
    "Omitted the caveat that this only applies to certain regions"
  ],
  "wording_comparison": {{
    "llm_claim": "The hotel opened in March 2017",
    "source_says": "Grand opening took place in March 2017",
    "faithful": true
  }},
  "confidence": 0.85,
  "reasoning": "The core fact (March 2017 opening) is accurate. The LLM used slightly different wording but preserved the essential meaning. Minor temporal precision issue noted but doesn't significantly affect accuracy."
}}"""

USER_PROMPT = """Verify if the LLM accurately interpreted its cited source.

LLM'S CLAIM:
{claim}

ORIGINAL TEXT FROM LLM OUTPUT:
{original_text}

EXTRACTED EXCERPTS FROM SOURCE:
{excerpts}

FULL SOURCE CONTENT (may be truncated):
{source_content}

INSTRUCTIONS:
1. Compare the LLM's claim against what the source actually says
2. Check if the excerpts accurately represent the source
3. Identify any distortions, omissions, or misinterpretations
4. Consider both the excerpts AND the full source context
5. Be fair - focus on substantive issues, not minor wording differences

{format_instructions}

Provide your verification assessment now."""


def get_llm_verification_prompts():
    """Return prompts for LLM output verification"""
    return {
        "system": SYSTEM_PROMPT,
        "user": USER_PROMPT
    }
