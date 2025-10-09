# agents/credibility_filter.py
"""
Credibility Filter Agent
Evaluates and filters web search results based on source credibility
"""

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import time

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config

class SourceEvaluation(BaseModel):
    """Evaluation of a single source's credibility"""
    url: str
    title: str
    credibility_score: float = Field(ge=0.0, le=1.0)
    credibility_tier: str
    reasoning: str
    strengths: List[str]
    concerns: List[str]
    recommended: bool

class CredibilityEvaluationOutput(BaseModel):
    """Output from credibility evaluation"""
    sources: List[Dict[str, Any]] = Field(description="List of evaluated sources")
    summary: Dict[str, int] = Field(description="Summary statistics")

class CredibilityResults:
    """Container for credibility evaluation results"""
    def __init__(self, fact_id: str, evaluations: List[SourceEvaluation], summary: Dict):
        self.fact_id = fact_id
        self.evaluations = evaluations
        self.summary = summary

    def get_recommended_urls(self, min_score: float = 0.70) -> List[str]:
        """Get URLs of sources with credibility score >= min_score"""
        return [
            eval.url for eval in self.evaluations
            if eval.credibility_score >= min_score
        ]

    def get_top_sources(self, n: int = 10) -> List[SourceEvaluation]:
        """Get top N sources by credibility score"""
        return sorted(
            self.evaluations,
            key=lambda x: x.credibility_score,
            reverse=True
        )[:n]

    def get_highly_credible(self) -> List[SourceEvaluation]:
        """Get sources with score >= 0.85"""
        return [e for e in self.evaluations if e.credibility_score >= 0.85]

class CredibilityFilter:
    """
    Evaluates source credibility for fact-checking
    
    Uses AI to analyze search results and filter based on:
    - Domain authority
    - Content quality
    - Editorial standards
    - Primary vs secondary sources
    """

    def __init__(self, config, min_credibility_score: float = 0.70):
        """
        Initialize credibility filter

        Args:
            config: Configuration object with OpenAI API key
            min_credibility_score: Minimum score for recommended sources (default: 0.70)
        """
        self.config = config
        self.min_credibility_score = min_credibility_score

        # Use GPT-4o for better credibility evaluation
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=CredibilityEvaluationOutput)

        # Load prompts
        from prompts.credibility_prompts import get_credibility_prompts
        self.prompts = get_credibility_prompts()

        # Statistics
        self.stats = {
            "total_evaluations": 0,
            "total_sources_evaluated": 0,
            "sources_recommended": 0,
            "sources_filtered_out": 0,
            "avg_credibility_score": 0.0
        }

        fact_logger.log_component_start(
            "CredibilityFilter",
            model="gpt-4o",
            min_score=min_credibility_score
        )

    @traceable(
        name="evaluate_source_credibility",
        run_type="chain",
        tags=["credibility", "filtering", "source-evaluation"]
    )
    async def evaluate_sources(
        self,
        fact,
        search_results: List[Dict[str, Any]]
    ) -> CredibilityResults:
        """
        Evaluate credibility of search results for a fact

        Args:
            fact: Fact object being verified
            search_results: List of search result dictionaries with url, title, content

        Returns:
            CredibilityResults with evaluations and recommendations
        """
        start_time = time.time()
        self.stats["total_evaluations"] += 1
        self.stats["total_sources_evaluated"] += len(search_results)

        fact_logger.logger.info(
            f"🔍 Evaluating credibility of {len(search_results)} sources for {fact.id}",
            extra={
                "fact_id": fact.id,
                "num_sources": len(search_results)
            }
        )

        if not search_results:
            fact_logger.logger.warning(
                f"⚠️ No search results to evaluate for {fact.id}",
                extra={"fact_id": fact.id}
            )
            return CredibilityResults(
                fact_id=fact.id,
                evaluations=[],
                summary={
                    "total_sources": 0,
                    "highly_credible": 0,
                    "credible": 0,
                    "moderately_credible": 0,
                    "low_credibility": 0,
                    "not_credible": 0,
                    "recommended_count": 0
                }
            )

        try:
            evaluation = await self._evaluate_sources_llm(fact, search_results)

            # Convert to SourceEvaluation objects
            evaluations = []
            for source_data in evaluation.sources:
                evaluations.append(SourceEvaluation(
                    url=source_data['url'],
                    title=source_data['title'],
                    credibility_score=source_data['credibility_score'],
                    credibility_tier=source_data['credibility_tier'],
                    reasoning=source_data['reasoning'],
                    strengths=source_data['strengths'],
                    concerns=source_data['concerns'],
                    recommended=source_data['recommended']
                ))

            results = CredibilityResults(
                fact_id=fact.id,
                evaluations=evaluations,
                summary=evaluation.summary
            )

            # Update statistics
            recommended = len(results.get_recommended_urls(self.min_credibility_score))
            self.stats["sources_recommended"] += recommended
            self.stats["sources_filtered_out"] += len(search_results) - recommended

            if evaluations:
                avg_score = sum(e.credibility_score for e in evaluations) / len(evaluations)
                self.stats["avg_credibility_score"] = avg_score

            duration = time.time() - start_time

            fact_logger.log_component_complete(
                "CredibilityFilter",
                duration,
                fact_id=fact.id,
                num_evaluated=len(evaluations),
                num_recommended=recommended
            )

            fact_logger.logger.info(
                f"✅ Credibility evaluation complete for {fact.id}",
                extra={
                    "fact_id": fact.id,
                    "total_sources": len(evaluations),
                    "recommended": recommended,
                    "filtered_out": len(evaluations) - recommended,
                    "avg_score": avg_score if evaluations else 0.0
                }
            )

            return results

        except Exception as e:
            fact_logger.log_component_error("CredibilityFilter", e, fact_id=fact.id)
            raise

    @traceable(name="evaluate_sources_llm", run_type="llm")
    async def _evaluate_sources_llm(
        self,
        fact,
        search_results: List[Dict]
    ) -> CredibilityEvaluationOutput:
        """
        Use LLM to evaluate source credibility

        Args:
            fact: Fact object
            search_results: List of search results

        Returns:
            CredibilityEvaluationOutput with evaluations
        """
        # Format search results for the prompt
        formatted_results = self._format_search_results(search_results)

        prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompts["system"] + "\n\nIMPORTANT: You MUST return valid JSON only. No other text."),
            ("user", self.prompts["user"] + "\n\n{format_instructions}\n\nReturn your response as valid JSON.")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks(f"credibility_filter_{fact.id}")

        chain = prompt_with_format | self.llm | self.parser

        fact_logger.logger.debug(
            f"🔗 Invoking LLM for credibility evaluation",
            extra={"fact_id": fact.id, "num_sources": len(search_results)}
        )

        response = await chain.ainvoke(
            {
                "fact": fact.statement,
                "search_results": formatted_results
            },
            config={"callbacks": callbacks.handlers}
        )

        return CredibilityEvaluationOutput(
            sources=response['sources'],
            summary=response['summary']
        )

    def _format_search_results(self, search_results: List[Dict]) -> str:
        """
        Format search results for the prompt

        Args:
            search_results: List of result dictionaries

        Returns:
            Formatted string for prompt
        """
        formatted = []

        for i, result in enumerate(search_results, 1):
            formatted.append(
                f"SOURCE #{i}:\n"
                f"URL: {result.get('url', 'N/A')}\n"
                f"Title: {result.get('title', 'N/A')}\n"
                f"Content Preview: {result.get('content', 'N/A')[:300]}...\n"
                f"Search Score: {result.get('score', 0.0)}\n"
            )

        return "\n".join(formatted)

    async def filter_and_rank_urls(
        self,
        fact,
        search_results: List[Dict],
        max_urls: int = 10
    ) -> List[str]:
        """
        Convenience method to evaluate and return top credible URLs

        Args:
            fact: Fact object
            search_results: Search results to evaluate
            max_urls: Maximum number of URLs to return

        Returns:
            List of top credible URLs
        """
        results = await self.evaluate_sources(fact, search_results)
        
        # Get recommended sources
        top_sources = results.get_top_sources(n=max_urls)
        
        # Filter by minimum credibility score
        filtered_urls = [
            s.url for s in top_sources
            if s.credibility_score >= self.min_credibility_score
        ]

        fact_logger.logger.info(
            f"🎯 Filtered to {len(filtered_urls)} credible URLs from {len(search_results)} total",
            extra={
                "fact_id": fact.id,
                "filtered_urls": len(filtered_urls),
                "total_sources": len(search_results)
            }
        )

        return filtered_urls

    def get_stats(self) -> Dict:
        """Return filtering statistics"""
        return self.stats.copy()

    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            "total_evaluations": 0,
            "total_sources_evaluated": 0,
            "sources_recommended": 0,
            "sources_filtered_out": 0,
            "avg_credibility_score": 0.0
        }
        fact_logger.logger.info("📊 Credibility filter statistics reset")
