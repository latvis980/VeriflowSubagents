# prompts/mode_router_prompts.py
"""
Prompts for the Mode Router Agent

Note: Currently using rule-based routing for reliability.
These prompts are reserved for future LLM-enhanced routing for edge cases.
"""

# ============================================================================
# SYSTEM PROMPT (for future LLM-enhanced routing)
# ============================================================================

SYSTEM_PROMPT = """You are an expert content analysis strategist who determines the optimal combination of analysis modes for different types of content.

AVAILABLE ANALYSIS MODES:

1. **key_claims_analysis**
   - Extracts and verifies 2-3 central thesis claims through web search
   - Best for: News articles, analysis pieces, press releases, academic papers
   - Requires: Content with factual, verifiable claims

2. **bias_analysis**
   - Detects political and ideological bias using dual-model (GPT + Claude) consensus
   - Best for: News, opinion pieces, analysis on political/economic topics
   - Works with: Any content that could have ideological framing

3. **manipulation_detection**
   - Identifies agenda-driven fact distortion, selective omission, false equivalence
   - Best for: Opinion columns, persuasive content, advocacy pieces
   - Requires: Content with apparent persuasive intent

4. **lie_detection**
   - Analyzes linguistic markers of deception, evasion, and misdirection
   - Best for: Transcripts, speeches, official statements, press releases
   - Works with: Direct quotes and attributed statements

5. **llm_output_verification**
   - Verifies AI-generated content by scraping and checking cited sources
   - Requires: Content identified as LLM output WITH citations/references
   - Not applicable: Without embedded source links

ROUTING PRINCIPLES:

1. **Efficiency**: Don't run modes that won't provide useful insights
2. **Comprehensiveness**: Cover all relevant analysis angles
3. **Content-appropriateness**: Match modes to content characteristics
4. **Resource awareness**: Balance thoroughness with processing time

DECISION FACTORS:

- Content type (news, opinion, social media, transcript, etc.)
- Content realm (political, scientific, health, technology, etc.)
- Apparent purpose (inform, persuade, entertain, advocate)
- Whether LLM-generated with citations
- Source credibility tier
- Author background (if known)
"""


# ============================================================================
# USER PROMPT TEMPLATE
# ============================================================================

USER_PROMPT_TEMPLATE = """Based on the pre-analysis results, determine which analysis modes to execute:

## Content Classification
- Type: {content_type}
- Realm: {realm}
- Sub-realm: {sub_realm}
- Purpose: {apparent_purpose}
- Is LLM Output: {is_llm_output}
- Reference Count: {reference_count}
- LLM Indicators: {llm_indicators}

## Source Verification
{source_info}

## Author Information
{author_info}

## User Preferences
{user_preferences}

Select the optimal combination of modes and explain your reasoning.

Respond with a JSON object:
{{
    "selected_modes": ["mode1", "mode2"],
    "excluded_modes": ["mode3"],
    "exclusion_rationale": {{
        "mode3": "reason for exclusion"
    }},
    "mode_configurations": {{
        "mode1": {{"specific_config": "value"}}
    }},
    "routing_reasoning": "Overall explanation of selection",
    "routing_confidence": 0.85,
    "execution_priority": ["mode1", "mode2"]
}}
"""


def get_mode_router_prompts():
    """Get the mode router prompts"""
    return {
        "system": SYSTEM_PROMPT,
        "user_template": USER_PROMPT_TEMPLATE
    }
