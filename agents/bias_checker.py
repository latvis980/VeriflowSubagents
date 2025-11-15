# agents/bias_checker.py
"""
Bias Checker Agent
Uses multiple LLMs (GPT-4o and Claude Sonnet) to detect bias in text,
then combines their assessments for a comprehensive analysis
"""

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import time
import asyncio

from prompts.bias_checker_prompts import get_bias_checker_prompts, get_combiner_prompts
from agents.publication_bias_detector import PublicationBiasDetector
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config


class BiasInstance(BaseModel):
    """A specific instance of bias detected"""
    type: str = Field(description="Type of bias (political, ideological, framing, etc.)")
    direction: str = Field(description="Direction of bias (e.g., 'left-leaning', 'right-leaning')")
    severity: int = Field(ge=1, le=10, description="Severity rating 1-10")
    evidence: str = Field(description="Specific evidence from the text")
    techniques: List[str] = Field(description="Rhetorical techniques used")


class BiasAnalysisResult(BaseModel):
    """Result from a single LLM's bias analysis"""
    model_name: str = Field(description="Which model performed the analysis")
    overall_bias_score: float = Field(ge=0.0, le=10.0, description="Overall bias score 0-10")
    primary_bias_direction: str = Field(description="Primary direction of bias")
    biases_detected: List[BiasInstance] = Field(description="List of specific biases found")
    balanced_aspects: List[str] = Field(description="What the text does well")
    missing_perspectives: List[str] = Field(description="Viewpoints not represented")
    recommendations: List[str] = Field(description="How to improve balance")
    reasoning: str = Field(description="Overall reasoning for the assessment")


class CombinedBiasReport(BaseModel):
    """Final combined bias assessment"""
    consensus_bias_score: float = Field(ge=0.0, le=10.0)
    consensus_direction: str
    areas_of_agreement: List[str]
    areas_of_disagreement: List[str]
    gpt_unique_findings: List[str]
    claude_unique_findings: List[str]
    publication_bias_context: Optional[str] = None
    final_assessment: str
    confidence: float = Field(ge=0.0, le=1.0)
    recommendations: List[str]


class BiasChecker:
    """
    Checks text for bias using multiple LLMs and combines results
    
    Workflow:
    1. Analyze text with GPT-4o
    2. Analyze text with Claude Sonnet (parallel)
    3. Detect publication bias (if metadata provided)
    4. Combine all analyses with GPT-4o
    5. Return comprehensive report
    """
    
    def __init__(self, config):
        self.config = config
        
        # Initialize GPT-4o for bias checking and combining
        self.gpt_llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.3  # Slightly higher for nuanced analysis
        ).bind(response_format={"type": "json_object"})
        
        # Initialize Claude Sonnet for bias checking
        self.claude_llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            temperature=0.3
        )
        
        # Initialize publication bias detector
        self.pub_detector = PublicationBiasDetector()
        
        # JSON parsers
        self.analysis_parser = JsonOutputParser(pydantic_object=BiasAnalysisResult)
        self.combiner_parser = JsonOutputParser(pydantic_object=CombinedBiasReport)
        
        # Load prompts
        self.bias_prompts = get_bias_checker_prompts()
        self.combiner_prompts = get_combiner_prompts()
        
        fact_logger.log_component_start(
            "BiasChecker",
            models=["gpt-4o", "claude-sonnet-4"]
        )
    
    @traceable(
        name="analyze_bias_gpt",
        run_type="chain",
        tags=["bias-detection", "gpt-4o"]
    )
    async def _analyze_with_gpt(self, text: str, publication_context: str) -> BiasAnalysisResult:
        """Analyze bias using GPT-4o"""
        fact_logger.logger.info("🤖 Analyzing bias with GPT-4o")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.bias_prompts["system"] + "\n\nIMPORTANT: You MUST return valid JSON only."),
            ("user", self.bias_prompts["user"] + "\n\n{format_instructions}")
        ])
        
        prompt_with_format = prompt.partial(
            format_instructions=self.analysis_parser.get_format_instructions()
        )
        
        callbacks = langsmith_config.get_callbacks("bias_checker_gpt")
        chain = prompt_with_format | self.gpt_llm | self.analysis_parser
        
        response = await chain.ainvoke(
            {
                "text": text,
                "publication_context": publication_context
            },
            config={"callbacks": callbacks.handlers}
        )
        
        # Add model name to response
        response["model_name"] = "gpt-4o"
        
        return BiasAnalysisResult(**response)
    
    @traceable(
        name="analyze_bias_claude",
        run_type="chain",
        tags=["bias-detection", "claude-sonnet"]
    )
    async def _analyze_with_claude(self, text: str, publication_context: str) -> BiasAnalysisResult:
        """Analyze bias using Claude Sonnet"""
        fact_logger.logger.info("🤖 Analyzing bias with Claude Sonnet")
        
        # Claude doesn't support OpenAI's strict JSON mode, so we emphasize JSON in the prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.bias_prompts["system"] + "\n\nCRITICAL: Return ONLY valid JSON. No markdown, no explanations, just the JSON object."),
            ("user", self.bias_prompts["user"] + "\n\n{format_instructions}\n\nReturn ONLY the JSON object, nothing else.")
        ])
        
        prompt_with_format = prompt.partial(
            format_instructions=self.analysis_parser.get_format_instructions()
        )
        
        callbacks = langsmith_config.get_callbacks("bias_checker_claude")
        chain = prompt_with_format | self.claude_llm | self.analysis_parser
        
        try:
            response = await chain.ainvoke(
                {
                    "text": text,
                    "publication_context": publication_context
                },
                config={"callbacks": callbacks.handlers}
            )
            
            # Add model name to response
            response["model_name"] = "claude-sonnet-4"
            
            return BiasAnalysisResult(**response)
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Claude analysis failed: {e}")
            # Return a fallback result
            return BiasAnalysisResult(
                model_name="claude-sonnet-4",
                overall_bias_score=5.0,
                primary_bias_direction="unknown",
                biases_detected=[],
                balanced_aspects=["Error occurred during analysis"],
                missing_perspectives=["Analysis incomplete due to error"],
                recommendations=["Re-run analysis"],
                reasoning=f"Analysis failed: {str(e)}"
            )
    
    @traceable(
        name="combine_bias_analyses",
        run_type="chain",
        tags=["bias-synthesis", "gpt-4o"]
    )
    async def _combine_analyses(
        self, 
        gpt_analysis: BiasAnalysisResult,
        claude_analysis: BiasAnalysisResult,
        publication_metadata: str
    ) -> CombinedBiasReport:
        """Combine multiple bias analyses into final report"""
        fact_logger.logger.info("🔄 Combining bias analyses")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.combiner_prompts["system"] + "\n\nIMPORTANT: You MUST return valid JSON only."),
            ("user", self.combiner_prompts["user"] + "\n\n{format_instructions}")
        ])
        
        prompt_with_format = prompt.partial(
            format_instructions=self.combiner_parser.get_format_instructions()
        )
        
        callbacks = langsmith_config.get_callbacks("bias_combiner")
        chain = prompt_with_format | self.gpt_llm | self.combiner_parser
        
        response = await chain.ainvoke(
            {
                "gpt_analysis": gpt_analysis.model_dump_json(indent=2),
                "claude_analysis": claude_analysis.model_dump_json(indent=2),
                "publication_metadata": publication_metadata
            },
            config={"callbacks": callbacks.handlers}
        )
        
        return CombinedBiasReport(**response)
    
    @traceable(
        name="check_bias_complete",
        run_type="chain",
        tags=["bias-detection", "multi-model", "complete-pipeline"]
    )
    async def check_bias(
        self, 
        text: str, 
        publication_name: Optional[str] = None
    ) -> Dict:
        """
        Complete bias checking pipeline
        
        Args:
            text: Text to analyze for bias
            publication_name: Optional name of publication for metadata lookup
            
        Returns:
            Dictionary with:
            - gpt_analysis: Raw GPT-4o analysis
            - claude_analysis: Raw Claude analysis
            - combined_report: Synthesized final report
            - publication_profile: Publication bias info (if available)
        """
        start_time = time.time()
        
        fact_logger.logger.info(
            "🔍 Starting bias analysis",
            extra={
                "text_length": len(text),
                "has_publication": publication_name is not None
            }
        )
        
        # Get publication context
        publication_context = self.pub_detector.get_publication_context(publication_name)
        publication_profile = self.pub_detector.detect_publication(publication_name)
        
        try:
            # Run both analyses in parallel
            fact_logger.logger.info("⚡ Running parallel bias analyses (GPT + Claude)")
            
            gpt_task = self._analyze_with_gpt(text, publication_context)
            claude_task = self._analyze_with_claude(text, publication_context)
            
            gpt_analysis, claude_analysis = await asyncio.gather(gpt_task, claude_task)
            
            # Combine analyses
            combined_report = await self._combine_analyses(
                gpt_analysis,
                claude_analysis,
                publication_context
            )
            
            duration = time.time() - start_time
            
            fact_logger.log_component_complete(
                "BiasChecker",
                duration,
                gpt_bias_score=gpt_analysis.overall_bias_score,
                claude_bias_score=claude_analysis.overall_bias_score,
                consensus_score=combined_report.consensus_bias_score
            )
            
            return {
                "gpt_analysis": gpt_analysis.model_dump(),
                "claude_analysis": claude_analysis.model_dump(),
                "combined_report": combined_report.model_dump(),
                "publication_profile": publication_profile.model_dump() if publication_profile else None,
                "processing_time": duration
            }
            
        except Exception as e:
            fact_logger.log_component_error("BiasChecker", e)
            raise
