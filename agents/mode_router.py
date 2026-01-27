# agents/mode_router.py
"""
Mode Router Agent
Decides which analysis modes to execute based on Stage 1 pre-analysis results

Used in Stage 1 of Comprehensive Analysis Mode to:
1. Analyze content classification results
2. Consider source credibility
3. Factor in author information
4. Select optimal combination of analysis modes

Available Modes:
- key_claims_analysis: Verify 2-3 main factual claims
- bias_analysis: Detect political/ideological bias
- manipulation_detection: Find agenda-driven fact distortion
- lie_detection: Analyze linguistic deception markers
- llm_output_verification: Verify AI-generated content with citations
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langsmith import traceable

from prompts.mode_router_prompts import get_mode_router_prompts
from utils.logger import fact_logger


# ============================================================================
# OUTPUT MODELS
# ============================================================================

class ModeSelection(BaseModel):
    """Result of mode routing decision"""
    
    # Selected modes to execute
    selected_modes: List[str] = Field(
        default_factory=list,
        description="List of mode IDs to execute: key_claims_analysis, bias_analysis, manipulation_detection, lie_detection, llm_output_verification"
    )
    
    # Excluded modes with rationale
    excluded_modes: List[str] = Field(
        default_factory=list,
        description="Modes that were considered but excluded"
    )
    exclusion_rationale: Dict[str, str] = Field(
        default_factory=dict,
        description="Reason each excluded mode was skipped"
    )
    
    # Mode-specific configurations
    mode_configurations: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Custom configurations for each selected mode"
    )
    
    # Routing reasoning
    routing_reasoning: str = Field(
        default="",
        description="Overall explanation of routing decision"
    )
    
    # Confidence
    routing_confidence: float = Field(
        default=0.8,
        ge=0.0, le=1.0,
        description="Confidence in mode selection"
    )
    
    # Priority order
    execution_priority: List[str] = Field(
        default_factory=list,
        description="Suggested order of execution (for display, not actual execution which is parallel)"
    )
    
    # Metadata
    routed_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


class ModeRouterResult(BaseModel):
    """Full result from mode routing including metadata"""
    selection: ModeSelection
    input_summary: Dict[str, Any]
    processing_time_ms: int
    success: bool
    error: Optional[str] = None


# ============================================================================
# MODE ROUTER AGENT
# ============================================================================

class ModeRouter:
    """
    Agent that determines which analysis modes to execute
    
    Takes Stage 1 results (content classification, source verification, author info)
    and decides the optimal combination of analysis modes.
    """
    
    def __init__(self):
        """Initialize the mode router agent"""
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",  # Faster model for routing decisions
            temperature=0.1
        )
        
        # Define available modes and their characteristics
        self.available_modes = {
            "key_claims_analysis": {
                "name": "Key Claims Analysis",
                "description": "Extracts and verifies 2-3 central thesis claims through web search",
                "best_for": ["news_article", "analysis_piece", "press_release", "academic_paper"],
                "realms": ["political", "economic", "scientific", "health", "environmental", "technology"],
                "requires_factual_claims": True
            },
            "bias_analysis": {
                "name": "Bias Analysis",
                "description": "Detects political and ideological bias using dual-model analysis",
                "best_for": ["news_article", "opinion_column", "analysis_piece", "blog_post"],
                "realms": ["political", "economic", "social", "international"],
                "requires_factual_claims": False
            },
            "manipulation_detection": {
                "name": "Manipulation Detection",
                "description": "Identifies agenda-driven fact distortion and manipulation techniques",
                "best_for": ["opinion_column", "analysis_piece", "blog_post", "social_media_post"],
                "purposes": ["persuade", "advocate"],
                "requires_factual_claims": True
            },
            "lie_detection": {
                "name": "Lie Detection",
                "description": "Analyzes linguistic markers of deception and evasion",
                "best_for": ["interview_transcript", "speech_transcript", "official_statement", "press_release"],
                "realms": ["political", "legal", "economic"],
                "requires_factual_claims": False
            },
            "llm_output_verification": {
                "name": "LLM Output Verification",
                "description": "Verifies AI-generated content by checking cited sources",
                "requires_llm_output": True,
                "requires_citations": True
            }
        }
        
        fact_logger.logger.info("✅ ModeRouter initialized")
    
    def _build_rule_based_selection(
        self,
        content_classification: Dict[str, Any],
        source_verification: Optional[Dict[str, Any]] = None,
        author_info: Optional[Dict[str, Any]] = None
    ) -> ModeSelection:
        """
        Rule-based mode selection as fallback/baseline
        
        This provides deterministic selection that can be enhanced by LLM reasoning
        """
        selected = []
        excluded = {}
        configurations = {}
        
        content_type = content_classification.get("content_type", "other")
        realm = content_classification.get("realm", "other")
        is_llm_output = content_classification.get("is_likely_llm_output", False)
        reference_count = content_classification.get("reference_count", 0)
        apparent_purpose = content_classification.get("apparent_purpose", "inform")
        
        # Rule 1: LLM Output Verification
        if is_llm_output and reference_count > 0:
            selected.append("llm_output_verification")
            configurations["llm_output_verification"] = {
                "reference_count": reference_count
            }
        elif is_llm_output:
            excluded["llm_output_verification"] = "LLM output detected but no citations to verify"
        
        # Rule 2: Key Claims Analysis
        factual_content_types = ["news_article", "analysis_piece", "press_release", "academic_paper", "official_statement"]
        factual_realms = ["political", "economic", "scientific", "health", "environmental", "technology", "international"]
        
        if content_type in factual_content_types or realm in factual_realms:
            selected.append("key_claims_analysis")
        else:
            excluded["key_claims_analysis"] = f"Content type '{content_type}' typically doesn't contain verifiable factual claims"
        
        # Rule 3: Bias Analysis
        bias_relevant_types = ["news_article", "opinion_column", "analysis_piece", "blog_post"]
        bias_relevant_realms = ["political", "economic", "social", "international"]
        
        if content_type in bias_relevant_types or realm in bias_relevant_realms:
            selected.append("bias_analysis")
            # Add source context if available
            if source_verification:
                configurations["bias_analysis"] = {
                    "source_context": source_verification.get("domain"),
                    "source_tier": source_verification.get("credibility_tier")
                }
        else:
            excluded["bias_analysis"] = f"Content realm '{realm}' is not typically subject to political/ideological bias"
        
        # Rule 4: Manipulation Detection
        manipulation_relevant_types = ["opinion_column", "analysis_piece", "blog_post", "social_media_post", "advertisement"]
        manipulation_purposes = ["persuade", "advocate", "advertise"]
        
        if content_type in manipulation_relevant_types or apparent_purpose in manipulation_purposes:
            selected.append("manipulation_detection")
        else:
            excluded["manipulation_detection"] = f"Content purpose '{apparent_purpose}' doesn't suggest manipulation risk"
        
        # Rule 5: Lie Detection
        lie_detection_types = ["interview_transcript", "speech_transcript", "official_statement", "press_release"]
        
        if content_type in lie_detection_types:
            selected.append("lie_detection")
        else:
            excluded["lie_detection"] = f"Content type '{content_type}' is not optimal for linguistic deception analysis"
        
        # Generate reasoning
        reasoning_parts = []
        reasoning_parts.append(f"Content classified as '{content_type}' in '{realm}' domain.")
        if is_llm_output:
            reasoning_parts.append(f"Detected as AI-generated with {reference_count} citations.")
        reasoning_parts.append(f"Purpose appears to be: {apparent_purpose}.")
        reasoning_parts.append(f"Selected {len(selected)} modes for comprehensive analysis.")
        
        return ModeSelection(
            selected_modes=selected,
            excluded_modes=list(excluded.keys()),
            exclusion_rationale=excluded,
            mode_configurations=configurations,
            routing_reasoning=" ".join(reasoning_parts),
            routing_confidence=0.85,
            execution_priority=selected  # Same as selected for rule-based
        )
    
    @traceable(name="mode_routing", run_type="chain", tags=["routing", "mode-selection"])
    async def route(
        self,
        content_classification: Dict[str, Any],
        source_verification: Optional[Dict[str, Any]] = None,
        author_info: Optional[Dict[str, Any]] = None,
        user_preferences: Optional[Dict[str, Any]] = None
    ) -> ModeRouterResult:
        """
        Determine which analysis modes to execute
        
        Args:
            content_classification: Result from ContentClassifier
            source_verification: Result from SourceVerifier (optional)
            author_info: Author research results (optional)
            user_preferences: User-specified mode preferences (optional)
        
        Returns:
            ModeRouterResult with selected modes and configurations
        """
        import time
        start_time = time.time()
        
        try:
            fact_logger.logger.info(
                "🎯 Starting mode routing",
                extra={
                    "content_type": content_classification.get("content_type"),
                    "realm": content_classification.get("realm"),
                    "is_llm": content_classification.get("is_likely_llm_output")
                }
            )
            
            # Use rule-based selection
            # (Can be enhanced with LLM reasoning for edge cases in future)
            selection = self._build_rule_based_selection(
                content_classification=content_classification,
                source_verification=source_verification,
                author_info=author_info
            )
            
            # Apply user preferences if provided
            if user_preferences:
                # Force include specific modes
                force_include = user_preferences.get("force_include", [])
                for mode in force_include:
                    if mode not in selection.selected_modes and mode in self.available_modes:
                        selection.selected_modes.append(mode)
                        if mode in selection.excluded_modes:
                            selection.excluded_modes.remove(mode)
                            selection.exclusion_rationale.pop(mode, None)
                
                # Force exclude specific modes
                force_exclude = user_preferences.get("force_exclude", [])
                for mode in force_exclude:
                    if mode in selection.selected_modes:
                        selection.selected_modes.remove(mode)
                        selection.excluded_modes.append(mode)
                        selection.exclusion_rationale[mode] = "Excluded by user preference"
            
            # Ensure at least one mode is selected
            if not selection.selected_modes:
                selection.selected_modes = ["key_claims_analysis"]  # Default fallback
                selection.routing_reasoning += " Defaulting to key claims analysis as baseline."
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            fact_logger.logger.info(
                f"✅ Mode routing complete: {selection.selected_modes}",
                extra={
                    "selected_count": len(selection.selected_modes),
                    "excluded_count": len(selection.excluded_modes),
                    "processing_time_ms": processing_time_ms
                }
            )
            
            return ModeRouterResult(
                selection=selection,
                input_summary={
                    "content_type": content_classification.get("content_type"),
                    "realm": content_classification.get("realm"),
                    "is_llm_output": content_classification.get("is_likely_llm_output"),
                    "has_source_verification": source_verification is not None,
                    "has_author_info": author_info is not None
                },
                processing_time_ms=processing_time_ms,
                success=True
            )
            
        except Exception as e:
            fact_logger.logger.error(f"❌ Mode routing failed: {e}")
            
            # Return default selection on error
            default_selection = ModeSelection(
                selected_modes=["key_claims_analysis"],
                excluded_modes=[],
                exclusion_rationale={},
                routing_reasoning=f"Error during routing, defaulting to key claims: {str(e)}",
                routing_confidence=0.5
            )
            
            return ModeRouterResult(
                selection=default_selection,
                input_summary={},
                processing_time_ms=int((time.time() - start_time) * 1000),
                success=False,
                error=str(e)
            )


# ============================================================================
# STANDALONE TESTING
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def test():
        router = ModeRouter()
        
        # Test 1: News article
        print("\n--- Test 1: News Article ---")
        result = await router.route(
            content_classification={
                "content_type": "news_article",
                "realm": "political",
                "is_likely_llm_output": False,
                "reference_count": 0,
                "apparent_purpose": "inform"
            }
        )
        print(f"Selected: {result.selection.selected_modes}")
        print(f"Excluded: {result.selection.excluded_modes}")
        
        # Test 2: LLM Output with citations
        print("\n--- Test 2: LLM Output ---")
        result = await router.route(
            content_classification={
                "content_type": "llm_output",
                "realm": "technology",
                "is_likely_llm_output": True,
                "reference_count": 5,
                "apparent_purpose": "inform"
            }
        )
        print(f"Selected: {result.selection.selected_modes}")
        print(f"Reasoning: {result.selection.routing_reasoning}")
        
        # Test 3: Opinion column
        print("\n--- Test 3: Opinion Column ---")
        result = await router.route(
            content_classification={
                "content_type": "opinion_column",
                "realm": "political",
                "is_likely_llm_output": False,
                "reference_count": 0,
                "apparent_purpose": "persuade"
            }
        )
        print(f"Selected: {result.selection.selected_modes}")
        print(f"Excluded: {result.selection.exclusion_rationale}")
    
    asyncio.run(test())
