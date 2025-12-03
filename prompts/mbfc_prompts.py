# prompts/mbfc_prompts.py
"""
Prompts for Media Bias/Fact Check (MBFC) Integration
Verifies correct publication match and extracts bias/credibility data
"""

# Prompt to verify if the scraped MBFC page matches the target publication
VERIFY_PUBLICATION_SYSTEM = """You are a precise verification assistant. Your ONLY task is to determine if a Media Bias/Fact Check (MBFC) page is about the CORRECT publication.

You will receive:
1. A target domain (e.g., "cnn.com", "foxnews.com", "nytimes.com")
2. Content scraped from an MBFC page

Your job:
- Check if the MBFC page is actually about the publication matching that domain
- Watch out for similar-sounding but different publications (e.g., "CNN" vs "CNN So Fake News")
- Watch out for imposter sites or parody sites
- The publication name in MBFC should match the domain provided

IMPORTANT: Return ONLY a JSON response with no other text."""

VERIFY_PUBLICATION_USER = """TARGET DOMAIN: {target_domain}

MBFC PAGE CONTENT:
{mbfc_content}

Is this MBFC page about the correct publication matching the domain "{target_domain}"?

Return ONLY valid JSON in this exact format:
{{
  "is_match": true or false,
  "publication_name": "Name found on MBFC page",
  "reason": "Brief explanation"
}}"""


# Prompt to extract structured bias data from MBFC page
EXTRACT_BIAS_SYSTEM = """You are a data extraction specialist. Your task is to extract structured bias and credibility information from Media Bias/Fact Check (MBFC) page content.

MBFC uses these standard ratings:
- Bias Rating: FAR LEFT, LEFT, LEFT-CENTER, CENTER, RIGHT-CENTER, RIGHT, FAR RIGHT (often with a numeric score like -3.6)
- Factual Reporting: VERY LOW, LOW, MOSTLY FACTUAL, HIGH, VERY HIGH (often with a numeric score)
- Credibility Rating: LOW CREDIBILITY, MEDIUM CREDIBILITY, HIGH CREDIBILITY
- Some sources may also have: CONSPIRACY-PSEUDOSCIENCE, QUESTIONABLE SOURCE, PRO-SCIENCE, SATIRE

Extract ALL available information. If a field is not found, use null.

IMPORTANT: Return ONLY a JSON response with no other text."""

EXTRACT_BIAS_USER = """MBFC PAGE CONTENT:
{mbfc_content}

Extract all bias and credibility information from this MBFC page.

Return ONLY valid JSON in this exact format:
{{
  "publication_name": "Full name of the publication",
  "bias_rating": "LEFT-CENTER, RIGHT, etc.",
  "bias_score": -3.6 or null if not found,
  "factual_reporting": "MOSTLY FACTUAL, HIGH, etc.",
  "factual_score": 3.7 or not found if not found,
  "credibility_rating": "MEDIUM CREDIBILITY, HIGH CREDIBILITY, etc.",
  "country": "USA, UK, etc.",
  "media_type": "TV Station/Website, Newspaper, etc.",
  "traffic_popularity": "High Traffic, Medium Traffic, etc.",
  "funding": "How it's funded (advertising, subscriptions, etc.)",
  "summary": "Brief 1-2 sentence summary of the MBFC assessment",
  "special_tags": ["QUESTIONABLE SOURCE", "CONSPIRACY-PSEUDOSCIENCE", etc. if applicable]
}}"""


def get_verify_prompts():
    """Return prompts for verifying publication match"""
    return {
        "system": VERIFY_PUBLICATION_SYSTEM,
        "user": VERIFY_PUBLICATION_USER
    }


def get_extract_prompts():
    """Return prompts for extracting bias data"""
    return {
        "system": EXTRACT_BIAS_SYSTEM,
        "user": EXTRACT_BIAS_USER
    }