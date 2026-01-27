# test_phase2_stage2.py
"""
Phase 2 Stage 2 Component Tests
Tests the Mode Router and Comprehensive Orchestrator

Run with: python test_phase2_stage2.py
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# TEST DATA
# ============================================================================

NEWS_ARTICLE = """
According to the Bureau of Labor Statistics, unemployment fell to 3.7% in November 2024, 
the lowest level since February. The economy added 199,000 jobs last month, exceeding 
economists' expectations of 150,000. However, wage growth remained stubbornly high at 
4.0% year-over-year, raising concerns about persistent inflation.

Federal Reserve Chair Jerome Powell indicated that the central bank remains committed 
to its 2% inflation target and suggested that interest rates may need to stay elevated 
for longer than previously anticipated. "We're not yet at a place where we can declare 
victory over inflation," Powell said in a press conference.

Critics argue that the Fed's aggressive rate hikes have disproportionately impacted 
lower-income households, while supporters contend that controlling inflation benefits 
all Americans in the long run.
"""

OPINION_COLUMN = """
The Biden administration's economic policies have been nothing short of disastrous for 
working Americans. Despite what the mainstream media would have you believe, inflation 
is still crushing family budgets while corporate profits soar to record heights.

The so-called "Inflation Reduction Act" was anything but - it was a massive giveaway 
to special interests dressed up in green packaging. Meanwhile, hardworking taxpayers 
are left footing the bill for electric vehicle subsidies that primarily benefit wealthy 
coastal elites.

It's time to hold this administration accountable for its failed economic experiment. 
The American people deserve better than empty promises and manipulated statistics.
"""

LLM_OUTPUT_WITH_CITATIONS = """
Climate change is accelerating faster than previously predicted, according to recent studies.

Global temperatures have risen approximately 1.2°C above pre-industrial levels [1]. 
The Intergovernmental Panel on Climate Change (IPCC) warns that we may reach the 
critical 1.5°C threshold by 2030 [2]. Arctic sea ice extent has declined by about 
13% per decade since satellite records began [3].

Scientists emphasize the need for immediate action to limit warming to 1.5°C to 
avoid the most catastrophic impacts [4].

Sources:
[1]: https://www.climate.gov/news-features/understanding-climate/climate-change-global-temperature
[2]: https://www.ipcc.ch/sr15/
[3]: https://nsidc.org/arcticseaicenews/
[4]: https://www.nature.com/articles/d41586-023-00800-z
"""

INTERVIEW_TRANSCRIPT = """
INTERVIEWER: Senator, did you have any knowledge of the campaign finance violations 
before they were reported?

SENATOR: Look, I've been very clear about this. My team handles all the day-to-day 
operations, and I trust them completely. I wasn't personally involved in any of the 
financial decisions that are now being questioned.

INTERVIEWER: But the emails suggest you were copied on several of these transactions.

SENATOR: I receive hundreds of emails daily. I can't possibly read every single one. 
What I can tell you is that I've always operated with complete integrity throughout 
my career. Anyone who knows me knows that.

INTERVIEWER: Will you cooperate fully with the investigation?

SENATOR: Absolutely. We have nothing to hide. My legal team is already in contact 
with the investigators, and we're confident this will all be cleared up very soon.
"""


# ============================================================================
# TEST: MODE ROUTER
# ============================================================================

async def test_mode_router():
    """Test the Mode Router agent"""
    print("\n" + "="*70)
    print("TESTING MODE ROUTER")
    print("="*70)

    from agents.mode_router import ModeRouter

    router = ModeRouter()

    # Test Case 1: News Article
    print("\n--- Test 1: News Article ---")
    result = await router.route(
        content_classification={
            "content_type": "news_article",
            "realm": "economic",
            "sub_realm": "employment",
            "is_likely_llm_output": False,
            "reference_count": 0,
            "apparent_purpose": "inform"
        },
        source_verification={
            "domain": "reuters.com",
            "credibility_tier": 1,
            "tier_label": "Official/Major News"
        }
    )
    print(f"  Selected Modes: {result.selection.selected_modes}")
    print(f"  Excluded: {result.selection.excluded_modes}")
    print(f"  Confidence: {result.selection.routing_confidence}")
    assert "key_claims_analysis" in result.selection.selected_modes
    assert "bias_analysis" in result.selection.selected_modes
    print("  ✅ PASSED")

    # Test Case 2: Opinion Column
    print("\n--- Test 2: Opinion Column ---")
    result = await router.route(
        content_classification={
            "content_type": "opinion_column",
            "realm": "political",
            "is_likely_llm_output": False,
            "reference_count": 0,
            "apparent_purpose": "persuade"
        }
    )
    print(f"  Selected Modes: {result.selection.selected_modes}")
    print(f"  Reasoning: {result.selection.routing_reasoning[:100]}...")
    assert "manipulation_detection" in result.selection.selected_modes
    assert "bias_analysis" in result.selection.selected_modes
    print("  ✅ PASSED")

    # Test Case 3: LLM Output with Citations
    print("\n--- Test 3: LLM Output with Citations ---")
    result = await router.route(
        content_classification={
            "content_type": "llm_output",
            "realm": "scientific",
            "is_likely_llm_output": True,
            "reference_count": 4,
            "apparent_purpose": "inform"
        }
    )
    print(f"  Selected Modes: {result.selection.selected_modes}")
    print(f"  Configurations: {result.selection.mode_configurations}")
    assert "llm_output_verification" in result.selection.selected_modes
    print("  ✅ PASSED")

    # Test Case 4: Interview Transcript
    print("\n--- Test 4: Interview Transcript ---")
    result = await router.route(
        content_classification={
            "content_type": "interview_transcript",
            "realm": "political",
            "is_likely_llm_output": False,
            "reference_count": 0,
            "apparent_purpose": "document"
        }
    )
    print(f"  Selected Modes: {result.selection.selected_modes}")
    assert "lie_detection" in result.selection.selected_modes
    print("  ✅ PASSED")

    # Test Case 5: User Preferences Override
    print("\n--- Test 5: User Preferences Override ---")
    result = await router.route(
        content_classification={
            "content_type": "news_article",
            "realm": "technology",
            "is_likely_llm_output": False,
            "reference_count": 0,
            "apparent_purpose": "inform"
        },
        user_preferences={
            "force_include": ["lie_detection"],
            "force_exclude": ["bias_analysis"]
        }
    )
    print(f"  Selected Modes: {result.selection.selected_modes}")
    assert "lie_detection" in result.selection.selected_modes
    assert "bias_analysis" not in result.selection.selected_modes
    print("  ✅ PASSED")

    print("\n✅ All Mode Router tests passed!")


# ============================================================================
# TEST: FULL STAGE 1 + MODE ROUTING INTEGRATION
# ============================================================================

async def test_stage1_to_routing():
    """Test Stage 1 classification flowing into Mode Routing"""
    print("\n" + "="*70)
    print("TESTING STAGE 1 → MODE ROUTING INTEGRATION")
    print("="*70)

    from agents.content_classifier import ContentClassifier
    from utils.source_verifier import SourceVerifier
    from agents.mode_router import ModeRouter

    classifier = ContentClassifier()
    verifier = SourceVerifier()
    router = ModeRouter()

    test_cases = [
        ("News Article", NEWS_ARTICLE),
        ("Opinion Column", OPINION_COLUMN),
        ("LLM Output", LLM_OUTPUT_WITH_CITATIONS),
        ("Interview", INTERVIEW_TRANSCRIPT)
    ]

    for name, content in test_cases:
        print(f"\n--- {name} ---")

        # Step 1: Classify
        class_result = await classifier.classify(content)
        c = class_result.classification
        print(f"  Classification: {c.content_type} ({c.realm})")
        print(f"  Is LLM: {c.is_likely_llm_output}, Refs: {c.reference_count}")

        # Step 2: Route
        route_result = await router.route(
            content_classification=c.model_dump(),
            source_verification=None
        )
        print(f"  Selected Modes: {route_result.selection.selected_modes}")
        print(f"  Reasoning: {route_result.selection.routing_reasoning[:80]}...")

    await verifier.close()
    print("\n✅ Stage 1 → Routing integration test complete!")


# ============================================================================
# TEST: COMPREHENSIVE ORCHESTRATOR (MOCK)
# ============================================================================

async def test_comprehensive_orchestrator_mock():
    """Test Comprehensive Orchestrator with mocked mode execution"""
    print("\n" + "="*70)
    print("TESTING COMPREHENSIVE ORCHESTRATOR (Stage 1 + Mode Routing)")
    print("="*70)

    # This test runs Stage 1 fully but doesn't execute the actual modes
    # (to avoid long processing times during testing)

    from agents.content_classifier import ContentClassifier
    from utils.source_verifier import SourceVerifier
    from agents.mode_router import ModeRouter
    from utils.job_manager import job_manager

    classifier = ContentClassifier()
    verifier = SourceVerifier()
    router = ModeRouter()

    # Create a test job (job_manager requires content argument)
    job_id = job_manager.create_job(content=NEWS_ARTICLE)
    print(f"  Job ID: {job_id}")

    # Run Stage 1 manually
    print("\n  Running Stage 1...")

    # 1a: Classification
    class_result = await classifier.classify(NEWS_ARTICLE)
    print(f"  ✅ Classification: {class_result.classification.content_type}")

    # 1b: Source verification (skip for test)
    print(f"  ⏭️ Source verification skipped (no URL)")

    # 1c: Mode routing
    route_result = await router.route(
        content_classification=class_result.classification.model_dump()
    )
    print(f"  ✅ Mode routing: {route_result.selection.selected_modes}")

    # Verify Stage 1 results
    assert class_result.success
    assert route_result.success
    assert len(route_result.selection.selected_modes) > 0

    print("\n  Stage 2 would execute these modes in parallel:")
    for mode in route_result.selection.selected_modes:
        print(f"    - {mode}")

    await verifier.close()
    print("\n✅ Comprehensive Orchestrator mock test complete!")


# ============================================================================
# MAIN
# ============================================================================

async def main():
    """Run all Phase 2 Stage 2 tests"""
    print("\n" + "="*70)
    print("PHASE 2 STAGE 2 COMPONENT TESTS")
    print("="*70)

    try:
        await test_mode_router()
    except Exception as e:
        print(f"\n❌ Mode Router test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        await test_stage1_to_routing()
    except Exception as e:
        print(f"\n❌ Stage 1 → Routing test failed: {e}")
        import traceback
        traceback.print_exc()

    try:
        await test_comprehensive_orchestrator_mock()
    except Exception as e:
        print(f"\n❌ Comprehensive Orchestrator test failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)
    print("ALL PHASE 2 TESTS COMPLETE")
    print("="*70 + "\n")


if __name__ == "__main__":
    asyncio.run(main())