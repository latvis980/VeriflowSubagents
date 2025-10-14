# agents/fact_checker.py
"""
Fact Checker Agent - UPDATED WITH TIER FILTERING
Compares claimed facts against source excerpts

✅ TIER FILTERING: Only uses Tier 1 (0.85-1.0) and Tier 2 (0.70-0.84) sources
✅ TIER PRECEDENCE: Tier 1 sources override Tier 2 when there are contradictions
"""

from langsmith import traceable
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
import time

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.source_metadata import SourceMetadata


class FactCheckResult(BaseModel):
    """Result of fact checking"""
    fact_id: str
    statement: str
    match_score: float = Field(ge=0.0, le=1.0)
    assessment: str
    discrepancies: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    tier_breakdown: Optional[Dict[str, int]] = None  # ✅ NEW: Track tier usage


class FactChecker:
    """
    Checks facts against extracted excerpts

    ✅ TIER FILTERING:
    - Discards Tier 3+ sources (< 0.70 credibility)
    - Only evaluates against Tier 1 (0.85-1.0) and Tier 2 (0.70-0.84)
    - Sorts excerpts by tier (Tier 1 first) before evaluation
    """

    def __init__(self, config):
        self.config = config
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=FactCheckResult)

        # Load prompts
        from prompts.checker_prompts import get_checker_prompts
        self.prompts = get_checker_prompts()

        fact_logger.log_component_start("FactChecker", model="gpt-4o")

    @traceable(
        name="check_fact_accuracy",
        run_type="chain",
        tags=["fact-checking", "verification", "tier-filtering"]
    )
    async def check_fact(
        self, 
        fact, 
        excerpts: dict,
        source_metadata: Optional[Dict[str, SourceMetadata]] = None
    ) -> FactCheckResult:
        """
        Compare fact against extracted excerpts with tier filtering

        ✅ TIER FILTERING: Only uses Tier 1 (0.85-1.0) and Tier 2 (0.70-0.84) sources
        Tier 3 and below are discarded

        Args:
            fact: Fact object with id, statement, sources
            excerpts: dict of {url: [excerpt_objects]}
            source_metadata: Optional dict of {url: SourceMetadata} with credibility tiers
        """
        start_time = time.time()

        # Compile all excerpts from all URLs into a single list
        all_excerpts = []
        for url, url_excerpts in excerpts.items():
            for excerpt in url_excerpts:
                all_excerpts.append({
                    "url": url,
                    "quote": excerpt['quote'],
                    "relevance": excerpt.get('relevance', 0.5)
                })

        # ✅ FILTER BY TIER: Only keep Tier 1 & Tier 2 sources
        tier_breakdown = {"tier1": 0, "tier2": 0, "tier3_plus_discarded": 0}

        if source_metadata:
            filtered_excerpts = []

            for excerpt in all_excerpts:
                url = excerpt['url']
                metadata = source_metadata.get(url)

                if metadata:
                    score = metadata.credibility_score

                    # Tier 1: 0.85-1.0, Tier 2: 0.70-0.84
                    if score >= 0.85:
                        excerpt['tier'] = 1
                        excerpt['credibility_score'] = score
                        filtered_excerpts.append(excerpt)
                        tier_breakdown["tier1"] += 1
                    elif score >= 0.70:
                        excerpt['tier'] = 2
                        excerpt['credibility_score'] = score
                        filtered_excerpts.append(excerpt)
                        tier_breakdown["tier2"] += 1
                    else:
                        # Discard Tier 3 and below
                        tier_breakdown["tier3_plus_discarded"] += 1
                        fact_logger.logger.debug(
                            f"🗑️ Discarding Tier 3+ excerpt from {metadata.name} (score: {score:.2f})"
                        )
                else:
                    # No metadata - keep by default, treat as Tier 2
                    excerpt['tier'] = 2
                    excerpt['credibility_score'] = 0.70
                    filtered_excerpts.append(excerpt)
                    tier_breakdown["tier2"] += 1

            fact_logger.logger.info(
                f"📊 Tier filtering for {fact.id}: Tier 1={tier_breakdown['tier1']}, "
                f"Tier 2={tier_breakdown['tier2']}, Discarded={tier_breakdown['tier3_plus_discarded']}",
                extra={
                    "fact_id": fact.id,
                    "tier1": tier_breakdown["tier1"],
                    "tier2": tier_breakdown["tier2"],
                    "discarded": tier_breakdown["tier3_plus_discarded"]
                }
            )

            all_excerpts = filtered_excerpts

        # ✅ SORT BY TIER: Tier 1 sources first, then Tier 2
        all_excerpts.sort(key=lambda x: x.get('tier', 2))

        fact_logger.logger.info(
            f"⚖️ Checking fact {fact.id}",
            extra={
                "fact_id": fact.id,
                "statement": fact.statement[:100],
                "num_excerpts": len(all_excerpts),
                "num_sources": len(excerpts)
            }
        )

        if not all_excerpts:
            fact_logger.logger.warning(
                f"⚠️ No Tier 1 or Tier 2 excerpts found for fact {fact.id}",
                extra={"fact_id": fact.id}
            )
            return FactCheckResult(
                fact_id=fact.id,
                statement=fact.statement,
                match_score=0.0,
                assessment="No Tier 1 or Tier 2 sources available for verification",
                discrepancies="All available sources were below credibility threshold (Tier 3+)",
                confidence=0.0,
                reasoning="Fact could not be verified - only low-credibility sources available",
                tier_breakdown=tier_breakdown
            )

        try:
            result = await self._evaluate_fact(fact, all_excerpts, source_metadata)
            result.tier_breakdown = tier_breakdown

            duration = time.time() - start_time

            fact_logger.log_component_complete(
                "FactChecker",
                duration,
                fact_id=fact.id,
                match_score=result.match_score,
                tier1_sources=tier_breakdown["tier1"],
                tier2_sources=tier_breakdown["tier2"]
            )

            return result

        except Exception as e:
            fact_logger.log_component_error("FactChecker", e, fact_id=fact.id)
            raise

    def _format_excerpts(self, excerpts: list, source_metadata: Optional[Dict[str, SourceMetadata]] = None) -> str:
        """
        Format excerpts for the prompt
        ✅ ENHANCED: Shows tier information and sorts by tier
        """
        formatted = []

        # Group by tier for clear separation
        tier1_excerpts = [e for e in excerpts if e.get('tier') == 1]
        tier2_excerpts = [e for e in excerpts if e.get('tier') == 2]

        # Format Tier 1 sources first
        if tier1_excerpts:
            formatted.append("=" * 60)
            formatted.append("TIER 1 SOURCES (HIGHEST CREDIBILITY - PRIMARY AUTHORITY)")
            formatted.append("=" * 60)

            for ex in tier1_excerpts:
                url = ex['url']
                metadata = source_metadata.get(url) if source_metadata else None

                if metadata:
                    formatted.append(
                        f"\n[Source: {metadata.name} ({metadata.source_type})]\n"
                        f"Credibility: {metadata.credibility_tier} (Score: {metadata.credibility_score:.2f})\n"
                        f"Relevance: {ex['relevance']}\n"
                        f"Quote: {ex['quote']}\n"
                        f"URL: {url}\n"
                    )
                else:
                    formatted.append(
                        f"\n[Source: {url}]\n"
                        f"Tier: 1\n"
                        f"Relevance: {ex['relevance']}\n"
                        f"Quote: {ex['quote']}\n"
                    )

        # Format Tier 2 sources next
        if tier2_excerpts:
            formatted.append("\n" + "=" * 60)
            formatted.append("TIER 2 SOURCES (CREDIBLE - SECONDARY AUTHORITY)")
            formatted.append("=" * 60)

            for ex in tier2_excerpts:
                url = ex['url']
                metadata = source_metadata.get(url) if source_metadata else None

                if metadata:
                    formatted.append(
                        f"\n[Source: {metadata.name} ({metadata.source_type})]\n"
                        f"Credibility: {metadata.credibility_tier} (Score: {metadata.credibility_score:.2f})\n"
                        f"Relevance: {ex['relevance']}\n"
                        f"Quote: {ex['quote']}\n"
                        f"URL: {url}\n"
                    )
                else:
                    formatted.append(
                        f"\n[Source: {url}]\n"
                        f"Tier: 2\n"
                        f"Relevance: {ex['relevance']}\n"
                        f"Quote: {ex['quote']}\n"
                    )

        return "\n".join(formatted)

    @traceable(name="evaluate_fact_match", run_type="llm")
    async def _evaluate_fact(self, fact, excerpts: list, source_metadata: Optional[Dict[str, SourceMetadata]] = None) -> FactCheckResult:
        """
        Evaluate fact accuracy against excerpts
        ✅ Emphasizes tier precedence in prompt

        Args:
            fact: Fact object
            excerpts: list of excerpt dicts with url, quote, relevance, tier
            source_metadata: Source metadata for tier information
        """
        # Format excerpts with tier separation
        excerpts_text = self._format_excerpts(excerpts, source_metadata)

        # ✅ Enhanced system prompt with tier precedence
        tier_precedence_note = """

⚠️ CRITICAL: TIER 1 SOURCES TAKE ABSOLUTE PRECEDENCE

When evaluating facts:
1. Prioritize Tier 1 sources (0.85-1.0 credibility) as the PRIMARY TRUTH
2. Use Tier 2 sources (0.70-0.84 credibility) only for supporting context
3. If Tier 1 and Tier 2 contradict, ALWAYS trust Tier 1
4. If only Tier 2 sources available, note this limitation in reasoning

Example: "While Tier 2 sources (Travel Blog) mention Chef Mario, Tier 1 sources (Official Restaurant Website, Michelin Guide) confirm Chef Julia is the current head chef. Tier 1 takes precedence."
"""

        system_prompt = self.prompts["system"] + tier_precedence_note + "\n\nIMPORTANT: You MUST return valid JSON only. No other text."

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", self.prompts["user"] + "\n\n{format_instructions}\n\nReturn your response as valid JSON.")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks(f"fact_checker_{fact.id}")

        chain = prompt_with_format | self.llm | self.parser

        fact_logger.logger.debug(
            f"🔗 Invoking LLM for fact checking",
            extra={"fact_id": fact.id, "num_excerpts": len(excerpts)}
        )

        response = await chain.ainvoke(
            {
                "fact": fact.statement,
                "excerpts": excerpts_text
            },
            config={"callbacks": callbacks.handlers}
        )

        # Parse and return
        return FactCheckResult(
            fact_id=fact.id,
            statement=fact.statement,
            match_score=response['match_score'],
            assessment=response['assessment'],
            discrepancies=response.get('discrepancies', 'None'),
            confidence=response['confidence'],
            reasoning=response['reasoning']
        )