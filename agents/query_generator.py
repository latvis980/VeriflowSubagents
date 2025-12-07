# agents/query_generator.py
"""
Query Generator Agent - ENHANCED VERSION
Converts factual claims into optimized Brave Search queries

ENHANCEMENTS:
- Accepts broad_context for content credibility awareness
- Accepts media_sources for source verification
- Accepts query_instructions for strategic guidance
- Can recommend Brave freshness parameter (pd/pw/pm/py)
- Context-aware query generation (hoax checking, official sources, etc.)
"""

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime
import time

from prompts.query_generator_prompts import get_query_generator_prompts, get_multilingual_query_prompts
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config

# Import the new context models (if available)
try:
    from agents.key_claims_extractor import BroadContext, QueryInstructions, ContentLocation
except ImportError:
    # Fallback definitions if import fails
    BroadContext = None
    QueryInstructions = None
    ContentLocation = None


class QueryGeneratorOutput(BaseModel):
    """Output from query generation"""
    primary_query: str = Field(description="Main search query")
    alternative_queries: List[str] = Field(description="Alternative query variations")
    search_focus: str = Field(description="What aspect the queries focus on")
    key_terms: List[str] = Field(description="Key search terms extracted")
    expected_sources: List[str] = Field(description="Types of sources expected")
    local_language_used: Optional[str] = Field(default=None, description="Local language if multilingual")
    recommended_freshness: Optional[str] = Field(default=None, description="Brave freshness param: pd/pw/pm/py")


class QueryGeneratorResult(BaseModel):
    """Complete query generation result"""
    queries: QueryGeneratorOutput
    fact_id: str
    generated_at: str

class SearchQueries(BaseModel):
    """Container for all search queries for a fact"""
    fact_id: str
    fact_statement: str
    primary_query: str
    alternative_queries: List[str]
    all_queries: List[str]
    search_focus: str
    key_terms: List[str]
    expected_sources: List[str]
    local_language_used: Optional[str] = None
    recommended_freshness: Optional[str] = None

    @property
    def query_count(self) -> int:
        """Number of queries generated"""
        return len(self.all_queries)

class QueryGenerator:
    """
    Generate optimized search queries for fact verification
    
    ENHANCED: Now accepts content analysis context for smarter query generation:
    - broad_context: Credibility assessment
    - media_sources: Sources mentioned in content
    - query_instructions: Strategic guidance
    """

    def __init__(self, config):
        self.config = config

        # Using GPT-4o-mini for query generation (fast + cost-effective)
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.1  # Slight creativity for query variations
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=QueryGeneratorOutput)
        self.prompts = get_query_generator_prompts()
        self.multilingual_prompts = get_multilingual_query_prompts()

        fact_logger.log_component_start(
            "QueryGenerator",
            model="gpt-4o-mini"
        )

    def _get_current_date_info(self) -> dict:
        """Get current date information for temporal awareness"""
        now = datetime.now()
        return {
            "current_date": now.strftime("%B %d, %Y"),
            "current_year": str(now.year),
            "current_month": now.strftime("%B"),
            "timestamp": now.isoformat()
        }

    def _build_temporal_context(self, publication_date: Optional[str] = None) -> str:
        """Build temporal context string for the prompt"""
        if publication_date:
            return f"PUBLICATION DATE: {publication_date}\nUse this date as the temporal reference for relative time expressions in the fact."
        return "No specific publication date provided. Use current date context for any relative time references."

    def _format_broad_context(self, broad_context) -> str:
        """Format broad_context for the prompt"""
        if broad_context is None:
            return "No content analysis available."
        
        # Handle both dict and Pydantic model
        if hasattr(broad_context, 'model_dump'):
            ctx = broad_context.model_dump()
        elif isinstance(broad_context, dict):
            ctx = broad_context
        else:
            return "No content analysis available."
        
        lines = [
            f"Content Type: {ctx.get('content_type', 'unknown')}",
            f"Credibility: {ctx.get('credibility_assessment', 'unknown')}",
            f"Reasoning: {ctx.get('reasoning', 'N/A')}",
        ]
        
        red_flags = ctx.get('red_flags', [])
        if red_flags:
            lines.append(f"Red Flags: {', '.join(red_flags)}")
        
        positive = ctx.get('positive_indicators', [])
        if positive:
            lines.append(f"Positive Indicators: {', '.join(positive)}")
        
        return "\n".join(lines)

    def _format_media_sources(self, media_sources: List[str]) -> str:
        """Format media sources for the prompt"""
        if not media_sources:
            return "No media sources mentioned."
        return "\n".join(f"- {source}" for source in media_sources)

    def _format_query_instructions(self, query_instructions) -> str:
        """Format query instructions for the prompt"""
        if query_instructions is None:
            return "No specific instructions provided."
        
        # Handle both dict and Pydantic model
        if hasattr(query_instructions, 'model_dump'):
            qi = query_instructions.model_dump()
        elif isinstance(query_instructions, dict):
            qi = query_instructions
        else:
            return "No specific instructions provided."
        
        lines = [
            f"Primary Strategy: {qi.get('primary_strategy', 'standard verification')}",
            f"Temporal Guidance: {qi.get('temporal_guidance', 'recent')}",
        ]
        
        modifiers = qi.get('suggested_modifiers', [])
        if modifiers:
            lines.append(f"Suggested Modifiers: {', '.join(modifiers)}")
        
        priorities = qi.get('source_priority', [])
        if priorities:
            lines.append(f"Source Priority: {', '.join(priorities)}")
        
        special = qi.get('special_considerations', '')
        if special:
            lines.append(f"Special Considerations: {special}")
        
        return "\n".join(lines)

    @traceable(name="generate_queries", run_type="chain")
    async def generate_queries(
        self,
        fact,
        context: str = "",
        content_location: Optional[Any] = None,
        publication_date: Optional[str] = None,
        # NEW PARAMETERS
        broad_context: Optional[Any] = None,
        media_sources: Optional[List[str]] = None,
        query_instructions: Optional[Any] = None
    ) -> 'SearchQueries':  # <-- Note: Returns SearchQueries, not QueryGeneratorOutput
        """
        Generate search queries for a fact

        Returns:
            SearchQueries object with all_queries attribute
        """
        start_time = time.time()
        
        fact_logger.logger.info(
            f"🔍 Generating queries for {fact.id}",
            extra={
                "fact_id": fact.id,
                "has_context": bool(context),
                "has_location": content_location is not None,
                "has_broad_context": broad_context is not None,
                "has_query_instructions": query_instructions is not None,
                "num_media_sources": len(media_sources) if media_sources else 0
            }
        )

        use_multilingual = (
            content_location is not None and
            hasattr(content_location, 'language') and
            content_location.language and
            content_location.language.lower() not in ['english', 'en', '']
        )

        if use_multilingual:
            result = await self._generate_queries_multilingual(
                fact, context, content_location, publication_date,
                broad_context, media_sources, query_instructions
            )
        else:
            result = await self._generate_queries_llm(
                fact, context, publication_date,
                broad_context, media_sources, query_instructions
            )

        # === FIX: Combine all queries and return SearchQueries ===
        all_queries = [result.primary_query] + result.alternative_queries

        queries = SearchQueries(
            fact_id=fact.id,
            fact_statement=fact.statement,
            primary_query=result.primary_query,
            alternative_queries=result.alternative_queries,
            all_queries=all_queries,  # <-- This is what orchestrator needs
            search_focus=result.search_focus,
            key_terms=result.key_terms,
            expected_sources=result.expected_sources,
            local_language_used=result.local_language_used,
            recommended_freshness=result.recommended_freshness  # NEW field
        )

        duration = time.time() - start_time
        fact_logger.logger.info(
            f"✅ Generated {len(all_queries)} queries for {fact.id}",
            extra={
                "fact_id": fact.id,
                "duration_seconds": round(duration, 2),
                "num_queries": len(all_queries),
                "recommended_freshness": result.recommended_freshness
            }
        )

        return queries

    @traceable(name="generate_queries_llm", run_type="llm")
    async def _generate_queries_llm(
        self,
        fact,
        context: str,
        publication_date: Optional[str] = None,
        broad_context: Optional[Any] = None,
        media_sources: Optional[List[str]] = None,
        query_instructions: Optional[Any] = None
    ) -> QueryGeneratorOutput:
        """Generate search queries with enhanced context (English only)"""
        
        # Get current date info
        date_info = self._get_current_date_info()
        temporal_context = self._build_temporal_context(publication_date)

        # Format new context fields
        formatted_broad_context = self._format_broad_context(broad_context)
        formatted_media_sources = self._format_media_sources(media_sources or [])
        formatted_query_instructions = self._format_query_instructions(query_instructions)

        # Format system prompt with date info
        formatted_system = self.prompts["system"].format(
            current_date=date_info["current_date"],
            current_year=date_info["current_year"]
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", formatted_system + "\n\nIMPORTANT: You MUST return valid JSON only. No other text."),
            ("user", self.prompts["user"] + "\n\nReturn your response as valid JSON.")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks(f"query_generator_{fact.id}")
        chain = prompt_with_format | self.llm | self.parser

        fact_logger.logger.debug(
            "🔗 Invoking LLM for query generation (enhanced context)",
            extra={
                "fact_id": fact.id,
                "current_date": date_info["current_date"],
                "publication_date": publication_date,
                "has_broad_context": broad_context is not None
            }
        )

        response = await chain.ainvoke(
            {
                "fact": fact.statement,
                "context": context or "No additional context provided",
                "temporal_context": temporal_context,
                # NEW context fields
                "broad_context": formatted_broad_context,
                "media_sources": formatted_media_sources,
                "query_instructions": formatted_query_instructions
            },
            config={"callbacks": callbacks.handlers}
        )

        return QueryGeneratorOutput(
            primary_query=response['primary_query'],
            alternative_queries=response['alternative_queries'],
            search_focus=response['search_focus'],
            key_terms=response['key_terms'],
            expected_sources=response['expected_sources'],
            local_language_used=None,
            recommended_freshness=response.get('recommended_freshness')
        )

    @traceable(name="generate_queries_multilingual", run_type="llm")
    async def _generate_queries_multilingual(
        self,
        fact,
        context: str,
        content_location,
        publication_date: Optional[str] = None,
        broad_context: Optional[Any] = None,
        media_sources: Optional[List[str]] = None,
        query_instructions: Optional[Any] = None
    ) -> QueryGeneratorOutput:
        """Generate multilingual search queries with enhanced context"""
        
        # Get current date info
        date_info = self._get_current_date_info()
        temporal_context = self._build_temporal_context(publication_date)

        # Format new context fields
        formatted_broad_context = self._format_broad_context(broad_context)
        formatted_media_sources = self._format_media_sources(media_sources or [])
        formatted_query_instructions = self._format_query_instructions(query_instructions)

        # Format system prompt with date info
        formatted_system = self.multilingual_prompts["system"].format(
            current_date=date_info["current_date"],
            current_year=date_info["current_year"]
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", formatted_system + "\n\nIMPORTANT: You MUST return valid JSON only. No other text."),
            ("user", self.multilingual_prompts["user"] + "\n\n{format_instructions}\n\nReturn your response as valid JSON.")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks(f"query_generator_multilingual_{fact.id}")
        chain = prompt_with_format | self.llm | self.parser

        # Get language and country from content_location
        target_language = content_location.language if hasattr(content_location, 'language') else 'english'
        country = content_location.country if hasattr(content_location, 'country') else 'international'

        fact_logger.logger.debug(
            "🔗 Invoking LLM for multilingual query generation (enhanced context)",
            extra={
                "fact_id": fact.id,
                "target_language": target_language,
                "country": country,
                "has_broad_context": broad_context is not None
            }
        )

        response = await chain.ainvoke(
            {
                "fact": fact.statement,
                "context": context or "No additional context provided",
                "temporal_context": temporal_context,
                "target_language": target_language,
                "country": country,
                # NEW context fields
                "broad_context": formatted_broad_context,
                "media_sources": formatted_media_sources,
                "query_instructions": formatted_query_instructions
            },
            config={"callbacks": callbacks.handlers}
        )

        return QueryGeneratorOutput(
            primary_query=response['primary_query'],
            alternative_queries=response['alternative_queries'],
            search_focus=response['search_focus'],
            key_terms=response['key_terms'],
            expected_sources=response['expected_sources'],
            local_language_used=response.get('local_language_used', target_language),
            recommended_freshness=response.get('recommended_freshness')
        )
