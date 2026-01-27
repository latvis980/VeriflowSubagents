# agents/content_classifier.py
"""
Content Classifier Agent
Analyzes submitted content to determine type, realm, and characteristics

Used in Stage 1 of Comprehensive Analysis Mode to:
1. Classify content type (news, opinion, social media, LLM output, etc.)
2. Identify content realm (political, economic, scientific, etc.)
3. Detect if content has HTML/Markdown references (LLM output indicator)
4. Assess content characteristics for downstream mode routing

This agent runs FIRST in the comprehensive analysis pipeline and its output
informs which analysis modes should be applied to the content.
"""

import re
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langsmith import traceable

from prompts.content_classifier_prompts import get_content_classifier_prompts
from utils.logger import fact_logger


# ============================================================================
# OUTPUT MODELS
# ============================================================================

class ContentClassification(BaseModel):
    """Complete content classification result"""
    
    # Content Type
    content_type: str = Field(
        default="other",
        description="Type: news_article|opinion_column|analysis_piece|social_media_post|press_release|blog_post|academic_paper|interview_transcript|speech_transcript|llm_output|official_statement|advertisement|satire|other"
    )
    content_type_confidence: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Confidence in content type classification"
    )
    content_type_reasoning: str = Field(
        default="",
        description="Explanation for content type classification"
    )
    
    # Content Realm
    realm: str = Field(
        default="other",
        description="Primary topic realm: political|economic|scientific|health|social|environmental|international|legal|entertainment|sports|technology|military|other"
    )
    sub_realm: Optional[str] = Field(
        default=None,
        description="More specific category within the realm"
    )
    realm_confidence: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Confidence in realm classification"
    )
    
    # Reference Detection (critical for LLM output identification)
    has_html_references: bool = Field(
        default=False,
        description="Whether content contains HTML anchor tags with href"
    )
    has_markdown_references: bool = Field(
        default=False,
        description="Whether content contains markdown-style references"
    )
    reference_count: int = Field(
        default=0,
        description="Number of source references detected"
    )
    reference_urls: List[str] = Field(
        default_factory=list,
        description="List of URLs extracted from references"
    )
    
    # Language and Geography
    detected_language: str = Field(
        default="English",
        description="Primary language of the content"
    )
    detected_country: Optional[str] = Field(
        default=None,
        description="Geographic focus of the content"
    )
    geographic_scope: str = Field(
        default="unclear",
        description="Scope: local|national|international|unclear"
    )
    
    # Content Characteristics
    content_length: str = Field(
        default="medium",
        description="Length category: short|medium|long"
    )
    word_count_estimate: int = Field(
        default=0,
        description="Approximate word count"
    )
    formality_level: str = Field(
        default="formal",
        description="Formality: formal|informal|mixed"
    )
    apparent_purpose: str = Field(
        default="inform",
        description="Purpose: inform|persuade|entertain|advertise|document|analyze|advocate"
    )
    
    # LLM Output Detection
    is_likely_llm_output: bool = Field(
        default=False,
        description="Whether content appears to be AI-generated with citations"
    )
    llm_output_indicators: List[str] = Field(
        default_factory=list,
        description="Indicators suggesting LLM-generated content"
    )
    
    # Additional Analysis
    notable_characteristics: List[str] = Field(
        default_factory=list,
        description="Notable features of the content"
    )
    overall_confidence: float = Field(
        default=0.5,
        ge=0.0, le=1.0,
        description="Overall confidence in classification"
    )
    classification_notes: str = Field(
        default="",
        description="Additional observations"
    )
    
    # Metadata
    classified_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


class ContentClassifierResult(BaseModel):
    """Full result from content classification including processing metadata"""
    classification: ContentClassification
    raw_content_length: int
    processing_time_ms: int
    success: bool
    error: Optional[str] = None


# ============================================================================
# CONTENT CLASSIFIER AGENT
# ============================================================================

class ContentClassifier:
    """
    Agent that classifies content type, realm, and characteristics
    
    Used as the first stage in comprehensive analysis to:
    1. Determine what kind of content we're analyzing
    2. Identify the topic/domain
    3. Detect if it's LLM output with citations
    4. Inform which analysis modes should run
    """
    
    # Content length thresholds (words)
    SHORT_THRESHOLD = 200
    LONG_THRESHOLD = 1500
    
    # Max content for AI analysis
    MAX_CONTENT_LENGTH = 15000  # characters
    
    def __init__(self, config=None):
        """
        Initialize the Content Classifier
        
        Args:
            config: Configuration object with API keys
        """
        self.config = config
        
        # Initialize LLM
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",  # Fast and cost-effective for classification
            temperature=0
        ).bind(response_format={"type": "json_object"})
        
        # Load prompts
        prompts = get_content_classifier_prompts()
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", prompts["system"]),
            ("user", prompts["user"])
        ])
        
        fact_logger.logger.info("✅ ContentClassifier initialized")
    
    def _preprocess_reference_detection(self, content: str) -> dict:
        """
        Pre-process content to detect references before AI analysis
        This provides fast, deterministic detection of HTML/Markdown links
        
        Args:
            content: Raw content to analyze
            
        Returns:
            Dict with reference detection results
        """
        results = {
            "has_html_references": False,
            "has_markdown_references": False,
            "reference_count": 0,
            "reference_urls": []
        }
        
        # Detect HTML anchor tags: <a href="...">
        html_pattern = r'<\s*a\s+[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>'
        html_matches = re.findall(html_pattern, content, re.IGNORECASE)
        if html_matches:
            results["has_html_references"] = True
            results["reference_urls"].extend(html_matches)
        
        # Detect markdown reference links: [1]: https://...
        markdown_ref_pattern = r'^\s*\[(\d+)\]\s*:\s*(https?://[^\s]+)'
        markdown_matches = re.findall(markdown_ref_pattern, content, re.MULTILINE)
        if markdown_matches:
            results["has_markdown_references"] = True
            results["reference_urls"].extend([url for _, url in markdown_matches])
        
        # Detect inline markdown links: [text](url)
        inline_pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
        inline_matches = re.findall(inline_pattern, content)
        if inline_matches:
            results["has_markdown_references"] = True
            results["reference_urls"].extend([url for _, url in inline_matches])
        
        # Deduplicate URLs
        results["reference_urls"] = list(set(results["reference_urls"]))
        results["reference_count"] = len(results["reference_urls"])
        
        return results
    
    def _estimate_word_count(self, content: str) -> int:
        """Estimate word count"""
        return len(content.split())
    
    def _classify_length(self, word_count: int) -> str:
        """Classify content length based on word count"""
        if word_count < self.SHORT_THRESHOLD:
            return "short"
        elif word_count > self.LONG_THRESHOLD:
            return "long"
        return "medium"
    
    def _truncate_content(self, content: str) -> str:
        """Truncate content for AI analysis if too long"""
        if len(content) <= self.MAX_CONTENT_LENGTH:
            return content
        
        # Take beginning and end to capture intro and conclusion
        half = self.MAX_CONTENT_LENGTH // 2
        return (
            content[:half] + 
            "\n\n[... content truncated for analysis ...]\n\n" + 
            content[-half:]
        )
    
    @traceable(name="classify_content")
    async def classify(
        self, 
        content: str, 
        source_url: Optional[str] = None
    ) -> ContentClassifierResult:
        """
        Classify content type, realm, and characteristics
        
        Args:
            content: The content to classify
            source_url: Optional source URL for context
            
        Returns:
            ContentClassifierResult with full classification
        """
        import time
        start_time = time.time()
        
        try:
            fact_logger.logger.info(
                "🔍 Starting content classification",
                extra={"content_length": len(content), "has_url": bool(source_url)}
            )
            
            # Pre-process: detect references deterministically
            ref_detection = self._preprocess_reference_detection(content)
            
            # Estimate word count and length
            word_count = self._estimate_word_count(content)
            length_class = self._classify_length(word_count)
            
            # Truncate content for AI if needed
            content_for_ai = self._truncate_content(content)
            
            # Run AI classification
            chain = self.prompt | self.llm
            
            response = await chain.ainvoke({
                "content": content_for_ai,
                "source_url": source_url or "Not provided"
            })
            
            # Parse response
            import json
            ai_result = json.loads(response.content)
            
            # Build classification, merging deterministic detection with AI analysis
            classification = ContentClassification(
                # Content Type
                content_type=ai_result.get("content_type", "other"),
                content_type_confidence=ai_result.get("content_type_confidence", 0.5),
                content_type_reasoning=ai_result.get("content_type_reasoning", ""),
                
                # Realm
                realm=ai_result.get("realm", "other"),
                sub_realm=ai_result.get("sub_realm"),
                realm_confidence=ai_result.get("realm_confidence", 0.5),
                
                # References - use deterministic detection, enhanced by AI
                has_html_references=ref_detection["has_html_references"] or ai_result.get("has_html_references", False),
                has_markdown_references=ref_detection["has_markdown_references"] or ai_result.get("has_markdown_references", False),
                reference_count=max(ref_detection["reference_count"], ai_result.get("reference_count", 0)),
                reference_urls=ref_detection["reference_urls"] or ai_result.get("reference_urls", []),
                
                # Language and Geography
                detected_language=ai_result.get("detected_language", "English"),
                detected_country=ai_result.get("detected_country"),
                geographic_scope=ai_result.get("geographic_scope", "unclear"),
                
                # Content Characteristics
                content_length=length_class,
                word_count_estimate=word_count,
                formality_level=ai_result.get("formality_level", "formal"),
                apparent_purpose=ai_result.get("apparent_purpose", "inform"),
                
                # LLM Output Detection - combine deterministic and AI
                is_likely_llm_output=(
                    (ref_detection["has_html_references"] or ref_detection["has_markdown_references"]) 
                    or ai_result.get("is_likely_llm_output", False)
                ),
                llm_output_indicators=ai_result.get("llm_output_indicators", []),
                
                # Additional
                notable_characteristics=ai_result.get("notable_characteristics", []),
                overall_confidence=ai_result.get("overall_confidence", 0.5),
                classification_notes=ai_result.get("classification_notes", "")
            )
            
            # If we detected references deterministically, boost LLM output likelihood
            if ref_detection["reference_count"] > 0:
                if "Detected source references" not in classification.llm_output_indicators:
                    classification.llm_output_indicators.append(
                        f"Detected {ref_detection['reference_count']} source reference(s)"
                    )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            fact_logger.logger.info(
                f"✅ Content classified as {classification.content_type} ({classification.realm})",
                extra={
                    "content_type": classification.content_type,
                    "realm": classification.realm,
                    "is_llm_output": classification.is_likely_llm_output,
                    "reference_count": classification.reference_count,
                    "processing_time_ms": processing_time
                }
            )
            
            return ContentClassifierResult(
                classification=classification,
                raw_content_length=len(content),
                processing_time_ms=processing_time,
                success=True
            )
            
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            fact_logger.logger.error(f"❌ Content classification failed: {e}")
            
            # Return a fallback classification
            fallback = ContentClassification(
                content_type="other",
                realm="other",
                overall_confidence=0.1,
                classification_notes=f"Classification failed: {str(e)}"
            )
            
            return ContentClassifierResult(
                classification=fallback,
                raw_content_length=len(content),
                processing_time_ms=processing_time,
                success=False,
                error=str(e)
            )


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def get_content_classifier(config=None) -> ContentClassifier:
    """
    Factory function to get a ContentClassifier instance
    
    Args:
        config: Configuration object
        
    Returns:
        ContentClassifier instance
    """
    return ContentClassifier(config)


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    # Test content samples
    test_samples = [
        # News article
        """
        WASHINGTON — The Federal Reserve announced today that it will maintain 
        interest rates at their current level, citing ongoing concerns about 
        inflation. Fed Chair Jerome Powell stated that the committee remains 
        "data dependent" in its approach to monetary policy.
        """,
        
        # LLM output with references
        """
        According to recent reports, the global AI market is experiencing rapid growth.
        The market is expected to reach $1.8 trillion by 2030 <a href="https://example.com/ai-report">Source</a>.
        Major tech companies including Google, Microsoft, and OpenAI are leading this expansion
        [1]: https://techcrunch.com/ai-market
        [2]: https://reuters.com/technology
        """,
        
        # Opinion piece
        """
        It's time we face the uncomfortable truth: our education system is failing 
        our children. As a parent and educator for over 20 years, I've watched 
        standards decline while administrators focus on the wrong metrics. 
        We need radical change, not incremental adjustments.
        """
    ]
    
    async def test():
        classifier = ContentClassifier()
        
        for i, sample in enumerate(test_samples, 1):
            print(f"\n{'='*60}")
            print(f"TEST {i}")
            print('='*60)
            
            result = await classifier.classify(sample)
            
            print(f"Type: {result.classification.content_type}")
            print(f"Realm: {result.classification.realm}")
            print(f"Is LLM Output: {result.classification.is_likely_llm_output}")
            print(f"References: {result.classification.reference_count}")
            print(f"Confidence: {result.classification.overall_confidence}")
            print(f"Processing Time: {result.processing_time_ms}ms")
    
    asyncio.run(test())
