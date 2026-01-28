# agents/report_synthesizer.py
"""
Report Synthesizer Agent
Stage 3: Comprehensive Analysis Synthesis

SIMPLIFIED VERSION - Produces human-readable reports instead of complex structured data.

Analyzes all reports from Stage 1 and Stage 2 to create:
- Overall credibility score (0-100) and rating
- Human-readable summary (the main output)
- Key concerns and positive indicators
- Actionable recommendations

Uses GPT-4o for nuanced multi-report analysis.
"""

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time
import json

from prompts.report_synthesizer_prompts import get_report_synthesizer_prompts
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config


# ============================================================================
# SIMPLIFIED PYDANTIC OUTPUT MODEL
# ============================================================================

class SynthesisReport(BaseModel):
    """
    Simplified synthesis report - focuses on human-readable output.

    The main content is in 'summary' - a comprehensive narrative analysis.
    """

    # Core metrics
    overall_score: int = Field(
        ge=0, le=100,
        description="Overall credibility score 0-100"
    )
    overall_rating: str = Field(
        description="Rating: Highly Credible, Credible, Mixed, Low Credibility, or Unreliable"
    )
    confidence: int = Field(
        ge=0, le=100,
        description="How confident in this assessment 0-100"
    )

    # The main output - human readable summary
    summary: str = Field(
        description="A comprehensive 3-5 paragraph analysis summary in plain language explaining what was found, what it means, and what readers should know"
    )

    # Simple lists for structured data
    key_concerns: List[str] = Field(
        default_factory=list,
        description="Top 3-5 concerns about this content, if any (empty list if no concerns)"
    )
    positive_indicators: List[str] = Field(
        default_factory=list,
        description="Positive credibility indicators found (empty list if none)"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="2-4 actionable recommendations for the reader"
    )

    # Metadata
    modes_analyzed: List[str] = Field(
        default_factory=list,
        description="Which analysis modes were run"
    )
    analysis_notes: Optional[str] = Field(
        default=None,
        description="Any important notes about limitations or caveats"
    )


# ============================================================================
# REPORT SYNTHESIZER AGENT
# ============================================================================

class ReportSynthesizer:
    """
    Stage 3 Agent: Synthesizes all analysis reports into a human-readable assessment.

    Takes Stage 1 and Stage 2 results and produces a clear, readable report
    that general users can understand.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}

        # Initialize LLM - GPT-4o for nuanced multi-report analysis
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.3  # Slight temperature for more natural writing
        ).bind(response_format={"type": "json_object"})

        # Load prompts
        self.prompts = get_report_synthesizer_prompts()

        # Initialize parser
        self.parser = JsonOutputParser(pydantic_object=SynthesisReport)

        fact_logger.log_component_start(
            "ReportSynthesizer",
            model="gpt-4o"
        )

    def _format_content_classification(self, classification: Optional[Dict]) -> str:
        """Format content classification for prompt"""
        if not classification:
            return "Not available"

        return f"""
Content Type: {classification.get('content_type', 'Unknown')}
Realm: {classification.get('realm', 'Unknown')} / {classification.get('sub_realm', '')}
Purpose: {classification.get('purpose', 'Unknown')}
Contains References: {classification.get('contains_references', False)}
LLM Characteristics: {classification.get('llm_characteristics', {})}
"""

    def _format_source_verification(self, verification: Optional[Dict]) -> str:
        """Format source verification for prompt"""
        if not verification:
            return "Not available"

        if verification.get('error') or verification.get('status') == 'no_url_to_verify':
            return f"Source verification not performed: {verification.get('error', verification.get('status', 'Unknown'))}"

        return f"""
Domain: {verification.get('domain', 'Unknown')}
Credibility Tier: {verification.get('credibility_tier', 'Unknown')} - {verification.get('tier_description', '')}
Verification Source: {verification.get('verification_source', 'Unknown')}
Bias Rating: {verification.get('bias_rating', 'Unknown')}
Factual Reporting: {verification.get('factual_reporting', 'Unknown')}
Is Propaganda: {verification.get('is_propaganda', False)}
"""

    def _format_mode_routing(self, routing: Optional[Dict]) -> str:
        """Format mode routing for prompt"""
        if not routing:
            return "Not available"

        return f"""
Selected Modes: {routing.get('selected_modes', [])}
Excluded Modes: {routing.get('excluded_modes', [])}
Routing Reasoning: {routing.get('reasoning', 'Not provided')}
"""

    def _format_mode_reports(self, mode_reports: Dict[str, Any], mode_errors: Dict[str, str]) -> str:
        """Format all mode reports for the prompt"""
        sections = []

        # Key Claims Analysis
        if "key_claims_analysis" in mode_reports:
            kc = mode_reports["key_claims_analysis"]
            summary = kc.get("summary", {})
            sections.append(f"""
### KEY CLAIMS ANALYSIS
- Total Claims Checked: {summary.get('total_key_claims', 0)}
- Verified: {summary.get('verified_count', 0)}
- Partially Verified: {summary.get('partial_count', 0)}
- Unverified: {summary.get('unverified_count', 0)}
- Average Confidence: {summary.get('average_confidence', 0):.0%}
- Overall Assessment: {summary.get('overall_credibility', 'Unknown')}

Claims Detail:
{json.dumps(kc.get('key_claims', []), indent=2, default=str)[:3000]}
""")
        elif "key_claims_analysis" in mode_errors:
            sections.append(f"### KEY CLAIMS ANALYSIS\nFAILED: {mode_errors['key_claims_analysis']}")

        # Bias Analysis
        if "bias_analysis" in mode_reports:
            ba = mode_reports["bias_analysis"]
            analysis = ba.get("analysis", {})
            sections.append(f"""
### BIAS ANALYSIS
- Consensus Bias Score: {analysis.get('consensus_bias_score', 0)}/10
- Direction: {analysis.get('consensus_direction', 'Unknown')}
- Confidence: {analysis.get('confidence', 0):.0%}
- Assessment: {analysis.get('final_assessment', 'Unknown')}

GPT-4o Analysis: {ba.get('gpt4o_analysis', {}).get('assessment', 'N/A')}
Claude Analysis: {ba.get('claude_analysis', {}).get('assessment', 'N/A')}
""")
        elif "bias_analysis" in mode_errors:
            sections.append(f"### BIAS ANALYSIS\nFAILED: {mode_errors['bias_analysis']}")

        # Manipulation Detection
        if "manipulation_detection" in mode_reports:
            md = mode_reports["manipulation_detection"]
            sections.append(f"""
### MANIPULATION DETECTION
- Manipulation Score: {md.get('manipulation_score', 0)}/10
- Overall Assessment: {md.get('overall_assessment', 'Unknown')}
- Detected Agenda: {md.get('detected_agenda', 'None detected')}

Key Findings:
{json.dumps(md.get('key_findings', []), indent=2, default=str)[:2000]}
""")
        elif "manipulation_detection" in mode_errors:
            sections.append(f"### MANIPULATION DETECTION\nFAILED: {mode_errors['manipulation_detection']}")

        # Lie Detection
        if "lie_detection" in mode_reports:
            ld = mode_reports["lie_detection"]
            sections.append(f"""
### LIE DETECTION
- Deception Score: {ld.get('deception_likelihood_score', ld.get('overall_score', 0))}/10
- Overall Assessment: {ld.get('overall_assessment', 'Unknown')}
- Linguistic Red Flags: {ld.get('linguistic_red_flags', [])}
""")
        elif "lie_detection" in mode_errors:
            sections.append(f"### LIE DETECTION\nFAILED: {mode_errors['lie_detection']}")

        # LLM Output Verification
        if "llm_output_verification" in mode_reports:
            lv = mode_reports["llm_output_verification"]
            sections.append(f"""
### LLM OUTPUT VERIFICATION
- Total Citations Checked: {lv.get('total_claims', 0)}
- Verified: {lv.get('verified_count', 0)}
- Misrepresented: {lv.get('misrepresented_count', 0)}
- Not Found: {lv.get('not_found_count', 0)}
""")
        elif "llm_output_verification" in mode_errors:
            sections.append(f"### LLM OUTPUT VERIFICATION\nFAILED: {mode_errors['llm_output_verification']}")

        return "\n".join(sections) if sections else "No mode reports available"

    @traceable(
        name="synthesize_reports",
        run_type="chain",
        tags=["report-synthesizer", "stage3", "gpt-4o"]
    )
    async def synthesize(
        self,
        stage1_results: Dict[str, Any],
        stage2_results: Dict[str, Any]
    ) -> SynthesisReport:
        """
        Synthesize all analysis reports into a human-readable assessment.

        Args:
            stage1_results: Results from Stage 1 (classification, verification, routing)
            stage2_results: Results from Stage 2 (mode_reports, mode_errors)

        Returns:
            SynthesisReport with human-readable summary and key metrics
        """
        start_time = time.time()

        # Extract data
        content_classification = stage1_results.get("content_classification")
        source_verification = stage1_results.get("source_verification")
        mode_routing = stage1_results.get("mode_routing")

        mode_reports = stage2_results.get("mode_reports", {})
        mode_errors = stage2_results.get("mode_errors", {})

        fact_logger.logger.info(
            "🔬 Stage 3: Synthesizing reports",
            extra={
                "modes_completed": list(mode_reports.keys()),
                "modes_failed": list(mode_errors.keys())
            }
        )

        # Format inputs for prompt
        content_classification_str = self._format_content_classification(content_classification)
        source_verification_str = self._format_source_verification(source_verification)
        mode_routing_str = self._format_mode_routing(mode_routing)
        mode_reports_str = self._format_mode_reports(mode_reports, mode_errors)

        # Build prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompts["system"]),
            ("user", self.prompts["user"])
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        # Execute chain
        callbacks = langsmith_config.get_callbacks("report_synthesis")
        chain = prompt_with_format | self.llm | self.parser

        try:
            response = await chain.ainvoke(
                {
                    "content_classification": content_classification_str,
                    "source_verification": source_verification_str,
                    "mode_routing": mode_routing_str,
                    "mode_reports_formatted": mode_reports_str
                },
                config={"callbacks": callbacks}
            )

            # Add metadata
            response["modes_analyzed"] = list(mode_reports.keys())

            # Handle any failed modes
            if mode_errors:
                response["analysis_notes"] = f"Some analysis modes failed: {', '.join(mode_errors.keys())}"

            # Validate and create report
            synthesis_report = SynthesisReport(**response)

            duration = time.time() - start_time
            fact_logger.logger.info(
                "✅ Stage 3 synthesis complete",
                extra={
                    "duration": round(duration, 2),
                    "overall_score": synthesis_report.overall_score,
                    "overall_rating": synthesis_report.overall_rating,
                    "concerns_count": len(synthesis_report.key_concerns),
                    "positives_count": len(synthesis_report.positive_indicators)
                }
            )

            return synthesis_report

        except Exception as e:
            fact_logger.logger.error(f"❌ Report synthesis failed: {e}")

            # Return a fallback synthesis report on error
            return self._create_fallback_report(
                mode_reports, 
                mode_errors, 
                str(e)
            )

    def _create_fallback_report(
        self,
        mode_reports: Dict[str, Any],
        mode_errors: Dict[str, str],
        error_message: str
    ) -> SynthesisReport:
        """Create a basic fallback synthesis report when AI synthesis fails"""

        # Calculate basic metrics from available data
        concerns = []
        positives = []
        score = 50  # Start neutral

        # Check key claims if available
        if "key_claims_analysis" in mode_reports:
            kc = mode_reports["key_claims_analysis"]
            summary = kc.get("summary", {})
            avg_conf = summary.get("average_confidence", 0.5)
            verified = summary.get("verified_count", 0)
            total = summary.get("total_key_claims", 1)

            if avg_conf >= 0.7:
                score += 15
                positives.append(f"Key claims were verified with {avg_conf:.0%} average confidence")
            elif avg_conf < 0.4:
                score -= 20
                concerns.append(f"Low fact verification confidence ({avg_conf:.0%})")

        # Check bias if available
        if "bias_analysis" in mode_reports:
            bias = mode_reports["bias_analysis"]
            analysis = bias.get("analysis", {})
            bias_score = abs(analysis.get("consensus_bias_score", 0))

            if bias_score > 6:
                score -= 15
                direction = analysis.get("consensus_direction", "Unknown")
                concerns.append(f"Significant {direction} bias detected (score: {bias_score:.1f}/10)")
            elif bias_score < 3:
                positives.append("Low bias detected - content appears balanced")

        # Check manipulation if available
        if "manipulation_detection" in mode_reports:
            manip = mode_reports["manipulation_detection"]
            manip_score = manip.get("manipulation_score", 0)

            if manip_score > 6:
                score -= 20
                concerns.append(f"High manipulation indicators detected (score: {manip_score:.1f}/10)")
            elif manip_score < 3:
                positives.append("Low manipulation indicators - straightforward presentation")

        # Determine rating
        if score >= 80:
            rating = "Highly Credible"
        elif score >= 65:
            rating = "Credible"
        elif score >= 45:
            rating = "Mixed"
        elif score >= 25:
            rating = "Low Credibility"
        else:
            rating = "Unreliable"

        # Build fallback summary
        summary_parts = [
            f"This content has been assessed with a credibility rating of **{rating}** (score: {score}/100).",
            "",
            "**Note:** Full AI-powered synthesis was unavailable for this analysis. The assessment above is based on automated metrics from the individual analysis modes.",
            ""
        ]

        if concerns:
            summary_parts.append("**Key Concerns:**")
            for concern in concerns:
                summary_parts.append(f"• {concern}")
            summary_parts.append("")

        if positives:
            summary_parts.append("**Positive Indicators:**")
            for positive in positives:
                summary_parts.append(f"• {positive}")
            summary_parts.append("")

        summary_parts.append("Please review the detailed findings from each analysis mode below for more specific information.")

        return SynthesisReport(
            overall_score=max(0, min(100, score)),
            overall_rating=rating,
            confidence=40,  # Low confidence due to fallback
            summary="\n".join(summary_parts),
            key_concerns=concerns,
            positive_indicators=positives,
            recommendations=[
                "Review the individual mode reports for detailed findings",
                "Consider re-running the analysis if this issue persists",
                "Cross-reference key claims with additional sources"
            ],
            modes_analyzed=list(mode_reports.keys()),
            analysis_notes=f"AI synthesis failed: {error_message}. Using fallback metrics."
        )


# ============================================================================
# STANDALONE TESTING
# ============================================================================

if __name__ == "__main__":
    import asyncio
    import os
    from dotenv import load_dotenv

    load_dotenv()

    async def test():
        synthesizer = ReportSynthesizer()

        # Mock Stage 1 results
        stage1_results = {
            "content_classification": {
                "content_type": "news_article",
                "realm": "politics",
                "sub_realm": "domestic_policy",
                "purpose": "inform"
            },
            "source_verification": {
                "domain": "example.com",
                "credibility_tier": 2,
                "tier_description": "Generally reliable source",
                "bias_rating": "left-center"
            },
            "mode_routing": {
                "selected_modes": ["key_claims_analysis", "bias_analysis"],
                "excluded_modes": ["llm_output_verification"]
            }
        }

        # Mock Stage 2 results
        stage2_results = {
            "mode_reports": {
                "key_claims_analysis": {
                    "summary": {
                        "total_key_claims": 5,
                        "verified_count": 3,
                        "partial_count": 1,
                        "unverified_count": 1,
                        "average_confidence": 0.72,
                        "overall_credibility": "Mostly Credible"
                    }
                },
                "bias_analysis": {
                    "analysis": {
                        "consensus_bias_score": 3.5,
                        "consensus_direction": "Left-leaning",
                        "confidence": 0.75,
                        "final_assessment": "Moderate left bias detected in framing"
                    }
                }
            },
            "mode_errors": {}
        }

        result = await synthesizer.synthesize(stage1_results, stage2_results)

        print("\n" + "="*60)
        print("SYNTHESIS REPORT")
        print("="*60)
        print(f"Overall Score: {result.overall_score}/100")
        print(f"Rating: {result.overall_rating}")
        print(f"Confidence: {result.confidence}%")
        print(f"\n--- SUMMARY ---\n{result.summary}")
        print(f"\n--- KEY CONCERNS ({len(result.key_concerns)}) ---")
        for concern in result.key_concerns:
            print(f"  • {concern}")
        print(f"\n--- POSITIVE INDICATORS ({len(result.positive_indicators)}) ---")
        for pos in result.positive_indicators:
            print(f"  • {pos}")
        print(f"\n--- RECOMMENDATIONS ({len(result.recommendations)}) ---")
        for rec in result.recommendations:
            print(f"  • {rec}")
        print(f"\nModes Analyzed: {result.modes_analyzed}")
        if result.analysis_notes:
            print(f"Notes: {result.analysis_notes}")

    asyncio.run(test())