# agents/credibility_filter.py
"""
Simplified Credibility Filter - 3-Tier System
Evaluates sources using binary yes/no criteria
"""

from langsmith import traceable
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.source_metadata import SourceMetadata, SourceNameExtractor


class SourceEvaluation(BaseModel):
    """Single source evaluation"""
    url: str
    title: str
    credibility_score: float = Field(ge=0.0, le=1.0)
    credibility_tier: str
    reasoning: str
    recommended: bool


class CredibilityEvaluationOutput(BaseModel):
    """LLM output structure"""
    sources: List[Dict[str, Any]]
    summary: Dict[str, int]


class CredibilityResults:
    """Results from credibility evaluation"""

    def __init__(self, fact_id: str, evaluations: List[SourceEvaluation], 
                 summary: Dict[str, int], source_metadata: Dict[str, SourceMetadata]):
        self.fact_id = fact_id
        self.evaluations = evaluations
        self.summary = summary
        self.source_metadata = source_metadata

    def get_recommended_urls(self, min_score: float = 0.70) -> List[str]:
        """Get URLs of recommended sources"""
        return [e.url for e in self.evaluations if e.recommended and e.credibility_score >= min_score]

    def get_top_sources(self, n: int = 10) -> List[SourceEvaluation]:
        """Get top N sources by credibility score"""
        sorted_evals = sorted(self.evaluations, key=lambda x: x.credibility_score, reverse=True)
        return sorted_evals[:n]

    def get_tier1_sources(self) -> List[SourceEvaluation]:
        """Get Tier 1 sources (score >= 0.85)"""
        return [e for e in self.evaluations if e.credibility_score >= 0.85]

    def get_source_metadata_dict(self) -> Dict[str, SourceMetadata]:
        """Get dictionary mapping URL to SourceMetadata"""
        return self.source_metadata.copy()


class CredibilityFilter:
    """
    Simplified credibility evaluation using 3-tier system

    Tier 1 (0.90): Official sources, major news, Wikipedia
    Tier 2 (0.75): Established platforms with editorial standards
    Tier 3 (0.40): Discard - low quality sources
    """

    def __init__(self, config, min_credibility_score: float = 0.70):
        self.config = config
        self.min_credibility_score = min_credibility_score

        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=CredibilityEvaluationOutput)
        self.name_extractor = SourceNameExtractor(config)

        # Load simplified prompts
        from prompts.credibility_prompts import get_credibility_prompts
        self.prompts = get_credibility_prompts()

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
            min_score=min_credibility_score,
            system="3-tier-simplified"
        )

    @traceable(
        name="evaluate_source_credibility",
        run_type="chain",
        tags=["credibility", "3-tier", "simplified"]
    )
    async def evaluate_sources(
        self,
        fact,
        search_results: List[Dict[str, Any]]
    ) -> CredibilityResults:
        """
        Evaluate credibility using simplified 3-tier system

        Args:
            fact: Fact object being verified
            search_results: List of search result dicts with url, title, content

        Returns:
            CredibilityResults with tier assignments
        """
        start_time = time.time()
        self.stats["total_evaluations"] += 1
        self.stats["total_sources_evaluated"] += len(search_results)

        fact_logger.logger.info(
            f"🔍 Evaluating {len(search_results)} sources using 3-tier system for {fact.id}"
        )

        if not search_results:
            return CredibilityResults(
                fact_id=fact.id,
                evaluations=[],
                summary={"total_sources": 0, "tier1": 0, "tier2": 0, "tier3": 0, "recommended_count": 0},
                source_metadata={}
            )

        try:
            # Get tier assignments from LLM
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
                    recommended=source_data['recommended']
                ))

            # Extract source names
            fact_logger.logger.info(f"🏷️ Extracting source names for {len(evaluations)} sources")
            source_metadata = await self._extract_source_metadata(evaluations)

            results = CredibilityResults(
                fact_id=fact.id,
                evaluations=evaluations,
                summary=evaluation.summary,
                source_metadata=source_metadata
            )

            # Update stats
            recommended = len(results.get_recommended_urls(self.min_credibility_score))
            self.stats["sources_recommended"] += recommended
            self.stats["sources_filtered_out"] += len(search_results) - recommended

            duration = time.time() - start_time

            fact_logger.log_component_complete(
                "CredibilityFilter",
                duration,
                fact_id=fact.id,
                tier1=evaluation.summary.get('tier1', 0),
                tier2=evaluation.summary.get('tier2', 0),
                tier3=evaluation.summary.get('tier3', 0)
            )

            return results

        except Exception as e:
            fact_logger.log_component_error("CredibilityFilter", e, fact_id=fact.id)
            raise

    async def _extract_source_metadata(
        self,
        evaluations: List[SourceEvaluation]
    ) -> Dict[str, SourceMetadata]:
        """Extract source names and create metadata"""
        metadata_dict = {}

        for evaluation in evaluations:
            try:
                # Extract clean name
                source_name, source_type = await self.name_extractor.extract_name(
                    evaluation.title,
                    evaluation.url
                )

                metadata_dict[evaluation.url] = SourceMetadata(
                    url=evaluation.url,
                    name=source_name,
                    source_type=source_type,
                    credibility_score=evaluation.credibility_score,
                    credibility_tier=evaluation.credibility_tier
                )

                fact_logger.logger.debug(
                    f"📋 Created metadata: {source_name} ({source_type})"
                )

            except Exception as e:
                fact_logger.logger.warning(
                    f"⚠️ Failed to extract name for {evaluation.url}: {e}"
                )
                # Fallback to URL-based name
                domain = evaluation.url.split('/')[2].replace('www.', '')
                metadata_dict[evaluation.url] = SourceMetadata(
                    url=evaluation.url,
                    name=domain.title(),
                    source_type="Website",
                    credibility_score=evaluation.credibility_score,
                    credibility_tier=evaluation.credibility_tier
                )

        return metadata_dict

    @traceable(name="tier_classification", run_type="llm")
    async def _evaluate_sources_llm(self, fact, search_results: List[Dict]) -> CredibilityEvaluationOutput:
        """Call LLM to classify sources into tiers"""

        formatted_results = self._format_search_results(search_results)

        prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompts["system"]),
            ("user", self.prompts["user"] + "\n\n{format_instructions}")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks(f"credibility_filter_{fact.id}")
        chain = prompt_with_format | self.llm | self.parser

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
        """Format search results for prompt"""
        formatted = []

        for i, result in enumerate(search_results, 1):
            formatted.append(
                f"SOURCE #{i}:\n"
                f"URL: {result.get('url', 'N/A')}\n"
                f"Title: {result.get('title', 'N/A')}\n"
                f"Preview: {result.get('content', 'N/A')[:200]}...\n"
            )

        return "\n".join(formatted)

    async def filter_and_rank_urls(
        self,
        fact,
        search_results: List[Dict],
        max_urls: int = 10
    ) -> List[str]:
        """Evaluate and return top credible URLs"""
        results = await self.evaluate_sources(fact, search_results)
        top_sources = results.get_top_sources(n=max_urls)

        filtered_urls = [
            s.url for s in top_sources
            if s.credibility_score >= self.min_credibility_score
        ]

        fact_logger.logger.info(
            f"🎯 Filtered to {len(filtered_urls)} credible URLs from {len(search_results)} total"
        )

        return filtered_urls