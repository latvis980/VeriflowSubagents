# agents/lie_detector.py
"""
Lie Detector / Deception Marker Analyzer Agent
Analyzes text for linguistic markers of fake news and disinformation using Claude API
"""

from langchain_anthropic import ChatAnthropic
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import time

from prompts.lie_detector_prompts import get_lie_detector_prompts
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config


class MarkerCategory(BaseModel):
    """A specific category of deception markers"""
    category: str = Field(description="Marker category name")
    present: bool = Field(description="Whether this marker is present")
    severity: str = Field(description="LOW, MEDIUM, or HIGH")
    examples: List[str] = Field(description="Specific examples from text")
    explanation: str = Field(description="Why this matters")


class LieDetectionResult(BaseModel):
    """Result from lie detection analysis"""
    risk_level: str = Field(description="Overall risk: LOW, MEDIUM, or HIGH")
    credibility_score: int = Field(ge=0, le=100, description="0-100, where 100 = highly credible")
    markers_detected: List[MarkerCategory] = Field(description="Detected deception markers")
    positive_indicators: List[str] = Field(description="Signs of credible journalism")
    overall_assessment: str = Field(description="Summary assessment")
    conclusion: str = Field(description="Final conclusion about disinformation likelihood")
    reasoning: str = Field(description="Detailed reasoning for the assessment")


class LieDetector:
    """
    Analyzes text for linguistic markers of deception using Claude
    
    Workflow:
    1. Parse temporal context (publication date if available)
    2. Analyze text with Claude using linguistic markers framework
    3. Extract structured results
    4. Return comprehensive assessment
    """
    
    def __init__(self, config):
        self.config = config
        
        # Initialize Claude Sonnet
        self.claude_llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            temperature=0.3
        )
        
        # JSON parser
        self.parser = JsonOutputParser(pydantic_object=LieDetectionResult)
        
        # Load prompts
        self.prompts = get_lie_detector_prompts()
        
        fact_logger.log_component_start("LieDetector", model="claude-sonnet-4")
    
    def _parse_date(self, date_string: Optional[str]) -> Optional[datetime]:
        """
        Try to parse various date formats into datetime object
        
        Args:
            date_string: The date string to parse (can be None)
            
        Returns:
            datetime object if successful, None otherwise
        """
        if not date_string:
            return None
        
        # Common date formats to try
        formats = [
            "%Y-%m-%d",  # 2025-10-18
            "%Y-%m-%dT%H:%M:%S",  # 2025-10-18T14:30:00
            "%Y-%m-%dT%H:%M:%SZ",  # 2025-10-18T14:30:00Z
            "%Y-%m-%dT%H:%M:%S%z",  # 2025-10-18T14:30:00+00:00
            "%B %d, %Y",  # October 18, 2025
            "%b %d, %Y",  # Oct 18, 2025
            "%d %B %Y",  # 18 October 2025
            "%d %b %Y",  # 18 Oct 2025
            "%m/%d/%Y",  # 10/18/2025
            "%d/%m/%Y",  # 18/10/2025
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_string.strip(), fmt)
            except:
                continue
        
        # If no format worked, try to extract just the date part if it's an ISO string
        try:
            if 'T' in date_string:
                date_part = date_string.split('T')[0]
                return datetime.strptime(date_part, "%Y-%m-%d")
        except:
            pass
        
        return None
    
    def _build_temporal_context(self, publication_date: Optional[str], current_date: datetime) -> str:
        """
        Build temporal context string based on publication date
        
        Args:
            publication_date: The publication date string (can be None)
            current_date: The current datetime
            
        Returns a string explaining when the article was published and how much time has passed
        """
        if not publication_date:
            return "PUBLICATION DATE: Unknown (could not be extracted from the article)"
        
        try:
            # Try to parse the publication date
            parsed_date = self._parse_date(publication_date)
            
            if not parsed_date:
                return f"PUBLICATION DATE: {publication_date} (format unclear)"
            
            # Calculate time difference
            time_diff = current_date - parsed_date
            days_ago = time_diff.days
            
            # Format the date nicely
            pub_date_str = parsed_date.strftime("%B %d, %Y")
            
            # Build context based on how long ago
            if days_ago < 0:
                # Future date - suspicious!
                context = f"PUBLICATION DATE: {pub_date_str}\n"
                context += "⚠️ WARNING: This article claims to be published in the FUTURE. This is highly suspicious."
            elif days_ago == 0:
                context = f"PUBLICATION DATE: {pub_date_str} (TODAY)\n"
                context += "This is a brand new article published today."
            elif days_ago == 1:
                context = f"PUBLICATION DATE: {pub_date_str} (YESTERDAY)\n"
                context += "This is a very recent article from yesterday."
            elif days_ago < 7:
                context = f"PUBLICATION DATE: {pub_date_str} ({days_ago} days ago)\n"
                context += "This is a recent article from this week."
            elif days_ago < 30:
                weeks_ago = days_ago // 7
                context = f"PUBLICATION DATE: {pub_date_str} ({weeks_ago} week{'s' if weeks_ago > 1 else ''} ago)\n"
                context += "This is a recent article from this month."
            elif days_ago < 365:
                months_ago = days_ago // 30
                context = f"PUBLICATION DATE: {pub_date_str} ({months_ago} month{'s' if months_ago > 1 else ''} ago)\n"
                context += f"This article is {months_ago} month{'s' if months_ago > 1 else ''} old. Events described may now be verifiable."
            else:
                years_ago = days_ago // 365
                context = f"PUBLICATION DATE: {pub_date_str} ({years_ago} year{'s' if years_ago > 1 else ''} ago)\n"
                context += f"This is an older article from {years_ago} year{'s' if years_ago > 1 else ''} ago. Events described should now be well-documented and verifiable."
            
            return context
            
        except Exception as e:
            fact_logger.logger.warning(f"Error building temporal context: {e}")
            return f"PUBLICATION DATE: {publication_date}"
    
    @traceable(
        name="analyze_deception_markers",
        run_type="chain",
        tags=["lie-detection", "linguistic-analysis", "claude-sonnet"]
    )
    async def analyze(
        self, 
        text: str,
        url: Optional[str] = None,
        publication_date: Optional[str] = None
    ) -> LieDetectionResult:
        """
        Analyze text for deception markers
        
        Args:
            text: The article text to analyze
            url: Optional article URL
            publication_date: Optional publication date (if available)
            
        Returns:
            LieDetectionResult with comprehensive analysis
        """
        fact_logger.logger.info("🔍 Starting lie detection analysis")
        
        # Limit content to avoid token limits
        if len(text) > 20000:
            fact_logger.logger.info("⚠️ Content too long, truncating to 20000 characters")
            text = text[:20000]
        
        # Get current date
        current_date = datetime.now()
        current_date_str = current_date.strftime("%B %d, %Y")
        
        # Build temporal context
        temporal_context = self._build_temporal_context(publication_date, current_date)
        
        # Build article source context
        article_source = f"ARTICLE URL: {url}" if url else "ARTICLE SOURCE: Plain text input"
        
        # Create prompt with system prompt that includes current date
        system_prompt = self.prompts["system"].format(current_date=current_date_str)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + "\n\nCRITICAL: Return ONLY valid JSON. No markdown, no explanations, just the JSON object."),
            ("user", self.prompts["user"] + "\n\nReturn ONLY the JSON object, nothing else.")
        ])
        
        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )
        
        callbacks = langsmith_config.get_callbacks("lie_detector_claude")
        chain = prompt_with_format | self.claude_llm | self.parser
        
        try:
            response = await chain.ainvoke(
                {
                    "current_date": current_date_str,
                    "temporal_context": temporal_context,
                    "article_source": article_source,
                    "text": text
                },
                config={"callbacks": callbacks.handlers}
            )
            
            fact_logger.logger.info("✅ Lie detection analysis completed")
            
            return LieDetectionResult(**response)
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Lie detection analysis failed: {e}")
            # Return a fallback result
            return LieDetectionResult(
                risk_level="UNKNOWN",
                credibility_score=50,
                markers_detected=[],
                positive_indicators=["Analysis incomplete due to error"],
                overall_assessment=f"Analysis failed: {str(e)}",
                conclusion="Unable to complete analysis",
                reasoning=f"Error occurred: {str(e)}"
            )
