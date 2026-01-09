# agents/manipulation_detector.py
"""
Opinion Manipulation Detector Agent
Analyzes articles for fact manipulation, misrepresentation, and agenda-driven distortion

Pipeline stages:
1. Article Analysis - Detect agenda, political lean, summary
2. Fact Extraction - Extract facts with framing context
3. Manipulation Analysis - Compare verified facts to their presentation
4. Report Synthesis - Create comprehensive manipulation report

Uses GPT-4o for analysis stages, integrates with existing fact-checking pipeline.
"""

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import time

from prompts.manipulation_detector_prompts import (
    get_article_analysis_prompts,
    get_fact_extraction_prompts,
    get_manipulation_analysis_prompts,
    get_report_synthesis_prompts
)
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config


# ============================================================================
# PYDANTIC MODELS - Stage 1: Article Analysis
# ============================================================================

class ArticleSummary(BaseModel):
    """High-level article analysis from Stage 1"""
    main_thesis: str = Field(
        description="The central claim/argument of the article"
    )
    political_lean: str = Field(
        description="Political lean: far-left|left|center-left|center|center-right|right|far-right|unclear"
    )
    detected_agenda: str = Field(
        description="What the article is trying to convince readers to believe/feel/do"
    )
    opinion_fact_ratio: float = Field(
        ge=0.0, le=1.0,
        description="0.0 = all facts, 1.0 = all opinion"
    )
    target_audience: str = Field(
        description="Who this article seems written for"
    )
    emotional_tone: str = Field(
        description="Primary emotional tone: neutral|alarming|celebratory|angry|fearful|hopeful|outraged|etc."
    )
    rhetorical_strategies: List[str] = Field(
        default_factory=list,
        description="Key rhetorical techniques used in the article"
    )
    summary: str = Field(
        default="",
        description="Brief summary of the article content"
    )


# ============================================================================
# PYDANTIC MODELS - Stage 2: Fact Extraction
# ============================================================================

class ExtractedFact(BaseModel):
    """A fact extracted with its presentation context from Stage 2"""
    id: str = Field(description="Unique identifier for the fact (MF1, MF2, etc.)")
    statement: str = Field(description="The factual claim being made")
    original_text: str = Field(description="Exact quote from the article")
    framing: str = Field(description="How it's presented: neutral|positive|negative")
    context_given: List[str] = Field(
        default_factory=list,
        description="What context IS provided in the article"
    )
    context_potentially_omitted: List[str] = Field(
        default_factory=list,
        description="What context MIGHT be missing (to verify)"
    )
    manipulation_potential: str = Field(
        default="medium",
        description="Potential for manipulation: low|medium|high"
    )


class FactExtractionResult(BaseModel):
    """Complete output from fact extraction stage"""
    facts: List[ExtractedFact] = Field(description="List of 3-5 extracted facts")
    extraction_notes: str = Field(
        default="",
        description="Any notes about the extraction process"
    )


# ============================================================================
# PYDANTIC MODELS - Stage 3: Manipulation Analysis
# ============================================================================

class ManipulationFinding(BaseModel):
    """Analysis of how a single fact has been manipulated"""
    fact_id: str = Field(description="ID of the fact being analyzed")
    fact_statement: str = Field(description="The fact statement")
    
    # Truthfulness assessment
    truthfulness: str = Field(
        description="TRUE|PARTIALLY_TRUE|FALSE|UNVERIFIABLE"
    )
    truth_score: float = Field(
        ge=0.0, le=1.0,
        description="Truthfulness score from verification"
    )
    
    # Manipulation detection
    manipulation_detected: bool = Field(
        description="Whether manipulation was detected"
    )
    manipulation_types: List[str] = Field(
        default_factory=list,
        description="Types: misrepresentation|omission|cherry_picking|false_equivalence|strawman|emotional_manipulation"
    )
    manipulation_severity: str = Field(
        default="none",
        description="Severity: none|low|medium|high"
    )
    
    # Detailed findings
    what_was_omitted: List[str] = Field(
        default_factory=list,
        description="Critical context that was actually omitted"
    )
    how_it_serves_agenda: str = Field(
        default="",
        description="How the manipulation serves the detected agenda"
    )
    corrected_context: str = Field(
        default="",
        description="How this fact should be understood with full context"
    )
    
    # Evidence
    sources_used: List[str] = Field(
        default_factory=list,
        description="URLs used to verify this fact"
    )
    key_evidence: str = Field(
        default="",
        description="Key evidence from sources"
    )


# ============================================================================
# PYDANTIC MODELS - Stage 4: Final Report
# ============================================================================

class ManipulationReport(BaseModel):
    """Final comprehensive manipulation analysis report"""
    # Article context
    article_summary: ArticleSummary = Field(
        description="Summary from Stage 1"
    )
    
    # Overall scores
    overall_manipulation_score: float = Field(
        ge=0.0, le=10.0,
        description="Overall manipulation score 0-10"
    )
    score_justification: str = Field(
        description="Explanation of the score"
    )
    
    # Findings
    manipulation_techniques_used: List[str] = Field(
        default_factory=list,
        description="All manipulation techniques identified"
    )
    facts_analyzed: List[ManipulationFinding] = Field(
        default_factory=list,
        description="Detailed analysis of each fact"
    )
    
    # Balanced assessment
    what_article_got_right: List[str] = Field(
        default_factory=list,
        description="Fair points and accurate elements"
    )
    key_misleading_elements: List[str] = Field(
        default_factory=list,
        description="Main misleading aspects"
    )
    
    # Agenda analysis
    agenda_alignment_analysis: str = Field(
        default="",
        description="How manipulations serve the detected agenda"
    )
    
    # Recommendation
    reader_recommendation: str = Field(
        description="How readers should interpret this content"
    )

    narrative_summary: str = Field(
        default="",
        description="Human-readable 2-4 sentence summary of the analysis for general readers"
    )
    
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the analysis"
    )
    
    # Metadata
    processing_time: float = Field(
        default=0.0,
        description="Total processing time in seconds"
    )


# ============================================================================
# MAIN AGENT CLASS
# ============================================================================

class ManipulationDetector:
    """
    Detects opinion manipulation in articles through multi-stage analysis
    
    Workflow:
    1. Analyze article for agenda and political lean
    2. Extract facts with framing context
    3. (External) Verify facts via web search pipeline
    4. Analyze manipulation of each fact
    5. Synthesize final report
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
        # Initialize LLM - using GPT-4o for nuanced analysis
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        ).bind(response_format={"type": "json_object"})
        
        # Load prompts
        self.article_analysis_prompts = get_article_analysis_prompts()
        self.fact_extraction_prompts = get_fact_extraction_prompts()
        self.manipulation_analysis_prompts = get_manipulation_analysis_prompts()
        self.report_synthesis_prompts = get_report_synthesis_prompts()
        
        # Initialize parsers
        self.article_parser = JsonOutputParser(pydantic_object=ArticleSummary)
        self.fact_parser = JsonOutputParser(pydantic_object=FactExtractionResult)
        self.manipulation_parser = JsonOutputParser(pydantic_object=ManipulationFinding)
        self.report_parser = JsonOutputParser(pydantic_object=ManipulationReport)
        
        # Config
        self.max_input_chars = 50000  # ~12k tokens
        
        fact_logger.log_component_start(
            "ManipulationDetector",
            model="gpt-4o",
            max_facts=5
        )
    
    # ========================================================================
    # STAGE 1: Article Analysis
    # ========================================================================
    
    @traceable(
        name="analyze_article_agenda",
        run_type="chain",
        tags=["manipulation-detection", "agenda-analysis", "gpt-4o"]
    )
    async def analyze_article(
        self, 
        text: str, 
        source_info: str = "Unknown source"
    ) -> ArticleSummary:
        """
        Stage 1: Analyze article for agenda, political lean, and summary
        
        Args:
            text: Article content
            source_info: URL or source name if available
            
        Returns:
            ArticleSummary with detected agenda and analysis
        """
        start_time = time.time()
        
        fact_logger.logger.info(
            "📰 Stage 1: Analyzing article for agenda",
            extra={"text_length": len(text), "source": source_info}
        )
        
        # Truncate if too long
        if len(text) > self.max_input_chars:
            fact_logger.logger.warning(
                f"⚠️ Article too long ({len(text)} chars), truncating to {self.max_input_chars}"
            )
            text = text[:self.max_input_chars]
        
        # Build prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.article_analysis_prompts["system"]),
            ("user", self.article_analysis_prompts["user"])
        ])
        
        prompt_with_format = prompt.partial(
            format_instructions=self.article_parser.get_format_instructions()
        )
        
        # Execute chain
        callbacks = langsmith_config.get_callbacks("manipulation_article_analysis")
        chain = prompt_with_format | self.llm | self.article_parser
        
        try:
            response = await chain.ainvoke(
                {
                    "text": text,
                    "source_info": source_info
                },
                config={"callbacks": callbacks.handlers}
            )
            
            result = ArticleSummary(**response)
            
            duration = time.time() - start_time
            fact_logger.logger.info(
                "✅ Article analysis complete",
                extra={
                    "duration": round(duration, 2),
                    "political_lean": result.political_lean,
                    "opinion_ratio": result.opinion_fact_ratio
                }
            )
            
            return result
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Article analysis failed: {e}")
            # Return fallback
            return ArticleSummary(
                main_thesis="Analysis failed",
                political_lean="unclear",
                detected_agenda="Could not detect",
                opinion_fact_ratio=0.5,
                target_audience="Unknown",
                emotional_tone="unknown",
                rhetorical_strategies=[],
                summary=f"Analysis failed: {str(e)}"
            )
    
    # ========================================================================
    # STAGE 2: Fact Extraction with Framing
    # ========================================================================
    
    @traceable(
        name="extract_facts_with_framing",
        run_type="chain",
        tags=["manipulation-detection", "fact-extraction", "gpt-4o"]
    )
    async def extract_facts(
        self, 
        text: str, 
        article_summary: ArticleSummary
    ) -> List[ExtractedFact]:
        """
        Stage 2: Extract key facts with their framing context
        
        Args:
            text: Article content
            article_summary: Results from Stage 1
            
        Returns:
            List of ExtractedFact with framing analysis
        """
        start_time = time.time()
        
        fact_logger.logger.info(
            "🔍 Stage 2: Extracting facts with framing context",
            extra={"detected_agenda": article_summary.detected_agenda}
        )
        
        # Truncate if needed
        if len(text) > self.max_input_chars:
            text = text[:self.max_input_chars]
        
        # Build prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.fact_extraction_prompts["system"]),
            ("user", self.fact_extraction_prompts["user"])
        ])
        
        prompt_with_format = prompt.partial(
            format_instructions=self.fact_parser.get_format_instructions()
        )
        
        # Execute chain
        callbacks = langsmith_config.get_callbacks("manipulation_fact_extraction")
        chain = prompt_with_format | self.llm | self.fact_parser
        
        try:
            response = await chain.ainvoke(
                {
                    "text": text,
                    "detected_agenda": article_summary.detected_agenda,
                    "political_lean": article_summary.political_lean
                },
                config={"callbacks": callbacks.handlers}
            )
            
            # Parse facts
            facts = []
            for i, fact_data in enumerate(response.get('facts', []), 1):
                fact = ExtractedFact(
                    id=fact_data.get('id', f'MF{i}'),
                    statement=fact_data.get('statement', ''),
                    original_text=fact_data.get('original_text', ''),
                    framing=fact_data.get('framing', 'neutral'),
                    context_given=fact_data.get('context_given', []),
                    context_potentially_omitted=fact_data.get('context_potentially_omitted', []),
                    manipulation_potential=fact_data.get('manipulation_potential', 'medium')
                )
                facts.append(fact)
            
            duration = time.time() - start_time
            fact_logger.logger.info(
                "✅ Fact extraction complete",
                extra={
                    "duration": round(duration, 2),
                    "num_facts": len(facts)
                }
            )
            
            return facts
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Fact extraction failed: {e}")
            return []
    
    # ========================================================================
    # STAGE 3: Manipulation Analysis (per fact)
    # ========================================================================
    
    @traceable(
        name="analyze_fact_manipulation",
        run_type="chain",
        tags=["manipulation-detection", "manipulation-analysis", "gpt-4o"]
    )
    async def analyze_manipulation(
        self,
        fact: ExtractedFact,
        article_summary: ArticleSummary,
        verification_result: Dict[str, Any],
        source_excerpts: str
    ) -> ManipulationFinding:
        """
        Stage 3: Analyze manipulation of a single fact
        
        Args:
            fact: The extracted fact with framing
            article_summary: Article analysis from Stage 1
            verification_result: Results from fact-checking pipeline
            source_excerpts: Relevant excerpts from sources
            
        Returns:
            ManipulationFinding with detailed analysis
        """
        fact_logger.logger.info(
            f"🔬 Stage 3: Analyzing manipulation for fact {fact.id}",
            extra={"fact": fact.statement[:50]}
        )
        
        # Build prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.manipulation_analysis_prompts["system"]),
            ("user", self.manipulation_analysis_prompts["user"])
        ])
        
        prompt_with_format = prompt.partial(
            format_instructions=self.manipulation_parser.get_format_instructions()
        )
        
        # Execute chain
        callbacks = langsmith_config.get_callbacks("manipulation_analysis")
        chain = prompt_with_format | self.llm | self.manipulation_parser
        
        try:
            response = await chain.ainvoke(
                {
                    "fact_statement": fact.statement,
                    "original_text": fact.original_text,
                    "framing": fact.framing,
                    "detected_agenda": article_summary.detected_agenda,
                    "truth_score": verification_result.get('match_score', 0.5),
                    "verification_summary": verification_result.get('report', 'No verification data'),
                    "source_excerpts": source_excerpts,
                    "potentially_omitted_context": "\n".join(fact.context_potentially_omitted)
                },
                config={"callbacks": callbacks.handlers}
            )
            
            # Build result
            result = ManipulationFinding(
                fact_id=fact.id,
                fact_statement=fact.statement,
                truthfulness=response.get('truthfulness', 'UNVERIFIABLE'),
                truth_score=verification_result.get('match_score', 0.5),
                manipulation_detected=response.get('manipulation_detected', False),
                manipulation_types=response.get('manipulation_types', []),
                manipulation_severity=response.get('manipulation_severity', 'none'),
                what_was_omitted=response.get('what_was_omitted', []),
                how_it_serves_agenda=response.get('how_it_serves_agenda', ''),
                corrected_context=response.get('corrected_context', ''),
                sources_used=verification_result.get('sources_used', []),
                key_evidence=response.get('key_evidence', '')
            )
            
            fact_logger.logger.info(
                f"✅ Manipulation analysis complete for {fact.id}",
                extra={
                    "manipulation_detected": result.manipulation_detected,
                    "severity": result.manipulation_severity
                }
            )
            
            return result
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Manipulation analysis failed for {fact.id}: {e}")
            return ManipulationFinding(
                fact_id=fact.id,
                fact_statement=fact.statement,
                truthfulness="UNVERIFIABLE",
                truth_score=0.5,
                manipulation_detected=False,
                manipulation_types=[],
                manipulation_severity="none",
                what_was_omitted=[],
                how_it_serves_agenda=f"Analysis failed: {str(e)}",
                corrected_context="",
                sources_used=[],
                key_evidence=""
            )
    
    # ========================================================================
    # STAGE 4: Report Synthesis
    # ========================================================================
    
    @traceable(
        name="synthesize_manipulation_report",
        run_type="chain",
        tags=["manipulation-detection", "report-synthesis", "gpt-4o"]
    )
    async def synthesize_report(
        self,
        article_summary: ArticleSummary,
        facts: List[ExtractedFact],
        manipulation_findings: List[ManipulationFinding],
        processing_time: float
    ) -> ManipulationReport:
        """
        Stage 4: Synthesize final manipulation report
        
        Args:
            article_summary: Article analysis from Stage 1
            facts: Extracted facts from Stage 2
            manipulation_findings: Analysis results from Stage 3
            processing_time: Total time taken
            
        Returns:
            ManipulationReport with comprehensive analysis
        """
        start_time = time.time()
        
        fact_logger.logger.info(
            "📊 Stage 4: Synthesizing final report",
            extra={"num_findings": len(manipulation_findings)}
        )
        
        # Format facts summary
        facts_summary = self._format_facts_summary(facts, manipulation_findings)
        
        # Format manipulation findings
        manipulation_findings_str = self._format_manipulation_findings(manipulation_findings)
        
        # Build prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.report_synthesis_prompts["system"]),
            ("user", self.report_synthesis_prompts["user"])
        ])
        
        prompt_with_format = prompt.partial(
            format_instructions=self.report_parser.get_format_instructions()
        )
        
        # Execute chain
        callbacks = langsmith_config.get_callbacks("manipulation_report_synthesis")
        chain = prompt_with_format | self.llm | self.report_parser
        
        try:
            response = await chain.ainvoke(
                {
                    "main_thesis": article_summary.main_thesis,
                    "political_lean": article_summary.political_lean,
                    "detected_agenda": article_summary.detected_agenda,
                    "opinion_fact_ratio": article_summary.opinion_fact_ratio,
                    "emotional_tone": article_summary.emotional_tone,
                    "facts_summary": facts_summary,
                    "manipulation_findings": manipulation_findings_str
                },
                config={"callbacks": callbacks.handlers}
            )
            
            # Build final report
            report = ManipulationReport(
                article_summary=article_summary,
                overall_manipulation_score=response.get('overall_manipulation_score', 5.0),
                score_justification=response.get('score_justification', ''),
                manipulation_techniques_used=response.get('manipulation_techniques_used', []),
                facts_analyzed=manipulation_findings,
                what_article_got_right=response.get('what_article_got_right', []),
                key_misleading_elements=response.get('key_misleading_elements', []),
                agenda_alignment_analysis=response.get('agenda_alignment_analysis', ''),
                reader_recommendation=response.get('reader_recommendation', ''),
                narrative_summary=response.get('narrative_summary', ''),
                confidence=response.get('confidence', 0.7),
                processing_time=processing_time + (time.time() - start_time)
            )
            
            fact_logger.logger.info(
                "✅ Report synthesis complete",
                extra={
                    "manipulation_score": report.overall_manipulation_score,
                    "confidence": report.confidence
                }
            )
            
            return report
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Report synthesis failed: {e}")
            # Return a minimal report
            return ManipulationReport(
                article_summary=article_summary,
                overall_manipulation_score=5.0,
                score_justification=f"Report synthesis failed: {str(e)}",
                manipulation_techniques_used=[],
                facts_analyzed=manipulation_findings,
                what_article_got_right=[],
                key_misleading_elements=[],
                agenda_alignment_analysis="",
                reader_recommendation="Analysis incomplete. Please try again.",
                confidence=0.0,
                processing_time=processing_time
            )
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _format_facts_summary(
        self, 
        facts: List[ExtractedFact], 
        findings: List[ManipulationFinding]
    ) -> str:
        """Format facts and findings for the synthesis prompt"""
        lines = []
        
        findings_by_id = {f.fact_id: f for f in findings}
        
        for fact in facts:
            finding = findings_by_id.get(fact.id)
            lines.append(f"FACT {fact.id}: {fact.statement}")
            lines.append(f"  Framing: {fact.framing}")
            lines.append(f"  Manipulation potential: {fact.manipulation_potential}")
            
            if finding:
                lines.append(f"  Truthfulness: {finding.truthfulness} (score: {finding.truth_score:.2f})")
                lines.append(f"  Manipulation detected: {finding.manipulation_detected}")
                if finding.manipulation_types:
                    lines.append(f"  Types: {', '.join(finding.manipulation_types)}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_manipulation_findings(self, findings: List[ManipulationFinding]) -> str:
        """Format manipulation findings for the synthesis prompt"""
        lines = []
        
        for finding in findings:
            lines.append(f"--- FACT {finding.fact_id} ---")
            lines.append(f"Statement: {finding.fact_statement}")
            lines.append(f"Truthfulness: {finding.truthfulness} (score: {finding.truth_score:.2f})")
            lines.append(f"Manipulation detected: {finding.manipulation_detected}")
            
            if finding.manipulation_detected:
                lines.append(f"Manipulation types: {', '.join(finding.manipulation_types)}")
                lines.append(f"Severity: {finding.manipulation_severity}")
                
                if finding.what_was_omitted:
                    lines.append(f"What was omitted: {', '.join(finding.what_was_omitted)}")
                
                lines.append(f"How it serves agenda: {finding.how_it_serves_agenda}")
                lines.append(f"Corrected context: {finding.corrected_context}")
            
            lines.append("")
        
        return "\n".join(lines)
    
    # ========================================================================
    # CONVENIENCE METHOD: Full Analysis
    # ========================================================================
    
    async def analyze_for_manipulation(
        self,
        text: str,
        source_info: str = "Unknown source",
        verification_callback=None
    ) -> ManipulationReport:
        """
        Run complete manipulation analysis pipeline
        
        This is a convenience method that runs all stages. For integration
        with the orchestrator, use individual stage methods.
        
        Args:
            text: Article content
            source_info: URL or source name
            verification_callback: Async function to verify facts (optional)
                                   Signature: async def(fact: ExtractedFact) -> Dict
            
        Returns:
            Complete ManipulationReport
        """
        start_time = time.time()
        
        fact_logger.logger.info("🚀 Starting full manipulation analysis pipeline")
        
        # Stage 1: Article Analysis
        article_summary = await self.analyze_article(text, source_info)
        
        # Stage 2: Fact Extraction
        facts = await self.extract_facts(text, article_summary)
        
        if not facts:
            fact_logger.logger.warning("⚠️ No facts extracted, returning minimal report")
            return ManipulationReport(
                article_summary=article_summary,
                overall_manipulation_score=0.0,
                score_justification="No verifiable facts could be extracted from the article",
                manipulation_techniques_used=[],
                facts_analyzed=[],
                what_article_got_right=["Article may be purely opinion-based"],
                key_misleading_elements=[],
                agenda_alignment_analysis="",
                reader_recommendation="This article appears to contain no verifiable factual claims.",
                confidence=0.5,
                processing_time=time.time() - start_time
            )
        
        # Stage 3: Manipulation Analysis (with optional verification)
        manipulation_findings = []
        
        for fact in facts:
            # Get verification result if callback provided
            if verification_callback:
                verification_result = await verification_callback(fact)
                source_excerpts = verification_result.get('excerpts', 'No excerpts available')
            else:
                # Mock verification for standalone testing
                verification_result = {
                    'match_score': 0.5,
                    'report': 'Verification not performed',
                    'sources_used': []
                }
                source_excerpts = "No verification performed"
            
            finding = await self.analyze_manipulation(
                fact=fact,
                article_summary=article_summary,
                verification_result=verification_result,
                source_excerpts=source_excerpts
            )
            manipulation_findings.append(finding)
        
        # Stage 4: Report Synthesis
        report = await self.synthesize_report(
            article_summary=article_summary,
            facts=facts,
            manipulation_findings=manipulation_findings,
            processing_time=time.time() - start_time
        )
        
        fact_logger.logger.info(
            "✅ Full manipulation analysis complete",
            extra={
                "total_time": round(report.processing_time, 2),
                "manipulation_score": report.overall_manipulation_score
            }
        )
        
        return report
