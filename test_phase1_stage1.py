# tests/test_phase1_stage1.py
"""
Test script for Phase 1: Stage 1 Components

Tests:
1. ContentClassifier - Content type and realm detection
2. SourceVerifier - URL extraction and credibility checking

Run with: python tests/test_phase1_stage1.py
"""

import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================================
# TEST DATA
# ============================================================================

# News article (political)
NEWS_ARTICLE = """
WASHINGTON — President Biden announced sweeping new climate regulations today, 
setting ambitious targets to reduce carbon emissions by 50% by 2030. The 
Environmental Protection Agency will oversee implementation of the new rules, 
which have drawn both praise from environmental groups and criticism from 
industry leaders.

EPA Administrator Michael Regan stated that the regulations represent "the most 
significant climate action in American history." However, the U.S. Chamber of 
Commerce warned the measures could cost millions of jobs.

The new policy comes ahead of next month's international climate summit in Dubai.
"""

# LLM output with citations
LLM_OUTPUT = """
Based on my research, here are the key findings about renewable energy adoption:

The global renewable energy market is experiencing unprecedented growth. According to 
the International Energy Agency, solar power capacity increased by 50% in 2023 
<a href="https://www.iea.org/reports/renewables-2023">IEA Report</a>.

China leads global solar installation with over 500 GW capacity [1]. The United States 
follows with significant investments in both solar and wind energy [2].

Key statistics:
- Solar costs have dropped 89% since 2010
- Wind power is now the cheapest source of new electricity in many regions
- Global renewable investment reached $500 billion in 2023

[1]: https://www.reuters.com/business/energy/china-solar-capacity
[2]: https://www.nytimes.com/2024/01/us-renewable-energy-investment
"""

# Opinion column
OPINION_PIECE = """
It's time we face an uncomfortable truth: our obsession with standardized testing 
is destroying American education. As a teacher for over 20 years, I've watched 
creativity and critical thinking being sacrificed at the altar of test scores.

When did we decide that filling in bubbles was more important than learning to 
think? Our children deserve better. They deserve teachers who can inspire, not 
just drill test prep.

The data shows that countries with less testing often outperform us. Finland has 
virtually eliminated standardized tests and consistently ranks among the world's 
best education systems. Why aren't we paying attention?

We need to demand change from our school boards and legislators. Our children's 
futures depend on it.
"""

# Social media post
SOCIAL_MEDIA = """
🚨 BREAKING: Just heard from sources that the new iPhone 16 will have AI built 
directly into the camera!! This is going to change EVERYTHING 🤯

Can't believe Apple didn't announce this at WWDC. Drop a 🍎 if you're excited!

#Apple #iPhone16 #AI #TechNews
"""


# ============================================================================
# TESTS
# ============================================================================

async def test_content_classifier():
    """Test the ContentClassifier agent"""
    print("\n" + "="*70)
    print("TESTING CONTENT CLASSIFIER")
    print("="*70)
    
    from agents.content_classifier import ContentClassifier
    
    classifier = ContentClassifier()
    
    test_cases = [
        ("News Article", NEWS_ARTICLE, "news_article", "political"),
        ("LLM Output", LLM_OUTPUT, "llm_output", "technology"),  # or economic
        ("Opinion Piece", OPINION_PIECE, "opinion_column", "social"),
        ("Social Media", SOCIAL_MEDIA, "social_media_post", "technology"),
    ]
    
    for name, content, expected_type, expected_realm in test_cases:
        print(f"\n--- Testing: {name} ---")
        
        result = await classifier.classify(content)
        
        c = result.classification
        print(f"  Content Type: {c.content_type} (expected: {expected_type})")
        print(f"  Realm: {c.realm} (expected: {expected_realm})")
        print(f"  Is LLM Output: {c.is_likely_llm_output}")
        print(f"  Reference Count: {c.reference_count}")
        print(f"  Has HTML Refs: {c.has_html_references}")
        print(f"  Has MD Refs: {c.has_markdown_references}")
        print(f"  Confidence: {c.overall_confidence:.2f}")
        print(f"  Purpose: {c.apparent_purpose}")
        print(f"  Processing Time: {result.processing_time_ms}ms")
        
        if c.llm_output_indicators:
            print(f"  LLM Indicators: {c.llm_output_indicators}")
        
        # Basic validation
        type_match = c.content_type == expected_type
        print(f"  ✅ Type Match: {type_match}" if type_match else f"  ⚠️ Type Mismatch")


async def test_source_verifier():
    """Test the SourceVerifier utility"""
    print("\n" + "="*70)
    print("TESTING SOURCE VERIFIER")
    print("="*70)
    
    from utils.source_verifier import SourceVerifier
    
    verifier = SourceVerifier()
    
    # Test 1: URL extraction
    print("\n--- Test: URL Extraction ---")
    urls = verifier.extract_urls_from_content(LLM_OUTPUT)
    print(f"  Found {len(urls)} URLs:")
    for url in urls:
        print(f"    - {url}")
    
    # Test 2: Domain extraction
    print("\n--- Test: Domain Extraction ---")
    test_urls = [
        "https://www.reuters.com/article/test",
        "https://nytimes.com/2024/test",
        "http://bbc.co.uk/news/test",
    ]
    for url in test_urls:
        domain = verifier.extract_domain(url)
        print(f"  {url} → {domain}")
    
    # Test 3: Source verification (without actual API calls for testing)
    print("\n--- Test: Source Verification ---")
    print("  (Note: Full verification requires BRAVE_API_KEY and may be slow)")
    
    # Try verification with content
    result = await verifier.verify_source(content=LLM_OUTPUT, run_mbfc_if_missing=False)
    
    r = result.report
    print(f"  URLs Found: {len(result.urls_found)}")
    print(f"  Primary URL: {r.original_url}")
    print(f"  Domain: {r.domain}")
    print(f"  Tier: {r.credibility_tier}")
    print(f"  Verification Source: {r.verification_source}")
    print(f"  Success: {r.verification_successful}")
    print(f"  Processing Time: {result.processing_time_ms}ms")
    
    if r.error:
        print(f"  Error: {r.error}")
    
    await verifier.close()


async def test_integration():
    """Test ContentClassifier + SourceVerifier together"""
    print("\n" + "="*70)
    print("TESTING INTEGRATION (Stage 1 Pipeline)")
    print("="*70)
    
    from agents.content_classifier import ContentClassifier
    from utils.source_verifier import SourceVerifier
    
    classifier = ContentClassifier()
    verifier = SourceVerifier()
    
    print("\n--- Simulating Stage 1 Pipeline ---")
    print("Input: LLM Output with Citations\n")
    
    # Step 1: Classify content
    print("Step 1: Content Classification...")
    class_result = await classifier.classify(LLM_OUTPUT)
    c = class_result.classification
    
    print(f"  Type: {c.content_type}")
    print(f"  Realm: {c.realm}")
    print(f"  Is LLM Output: {c.is_likely_llm_output}")
    print(f"  References: {c.reference_count}")
    
    # Step 2: Verify source (if URLs found)
    print("\nStep 2: Source Verification...")
    if c.reference_urls:
        print(f"  Found {len(c.reference_urls)} reference URLs")
        verify_result = await verifier.verify_source(
            content=LLM_OUTPUT, 
            run_mbfc_if_missing=False
        )
        r = verify_result.report
        print(f"  Primary Source: {r.domain}")
        print(f"  Credibility Tier: {r.credibility_tier}")
    else:
        print("  No reference URLs to verify")
    
    # Step 3: Determine recommended modes (preview of Mode Router logic)
    print("\nStep 3: Mode Recommendation (Preview)...")
    recommended_modes = []
    
    if c.is_likely_llm_output and c.reference_count > 0:
        recommended_modes.append("llm_output_verification")
        print("  → LLM Output Verification (has citations to verify)")
    
    if c.content_type in ["news_article", "analysis_piece", "press_release"]:
        recommended_modes.append("key_claims_analysis")
        print("  → Key Claims Analysis (factual content)")
    
    if c.realm == "political" or c.apparent_purpose == "persuade":
        recommended_modes.append("bias_analysis")
        print("  → Bias Analysis (political/persuasive content)")
    
    if c.content_type == "opinion_column" or c.apparent_purpose in ["persuade", "advocate"]:
        recommended_modes.append("manipulation_detection")
        print("  → Manipulation Detection (opinion/persuasive)")
    
    if c.content_type in ["interview_transcript", "speech_transcript", "official_statement"]:
        recommended_modes.append("lie_detection")
        print("  → Lie Detection (statements to analyze)")
    
    print(f"\n  Recommended Modes: {recommended_modes}")
    
    await verifier.close()
    
    print("\n✅ Integration test complete!")


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("PHASE 1 STAGE 1 COMPONENT TESTS")
    print("="*70)
    
    try:
        await test_content_classifier()
    except Exception as e:
        print(f"\n❌ Content Classifier test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        await test_source_verifier()
    except Exception as e:
        print(f"\n❌ Source Verifier test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        await test_integration()
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*70)
    print("ALL TESTS COMPLETE")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
