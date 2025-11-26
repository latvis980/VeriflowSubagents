# agents/llm_output_verifier.py
"""
LLM Output Verifier Agent
Verifies if an LLM accurately interpreted its cited sources

USAGE: LLM Output Pipeline ONLY
- Checks interpretation accuracy, not source credibility
- Compares LLM's claim against actual source content
- NO tier filtering (sources already provided by LLM)
"""

from langsmith import traceable
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import time

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from agents.llm_fact_extractor import LLMClaim  # ✅ Import new type


class LLMVerificationResult(BaseModel):
    """Result of LLM output verification"""
    claim_id: str
    claim_text: str
    verification_score: float = Field(ge=0.0, le=1.0)
    assessment: str
    interpretation_issues: List[str] = Field(default_factory=list)
    wording_comparison: Dict
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class LLMOutputVerifier:
    """
    Verifies if an LLM accurately interpreted its cited sources

    Key Difference from FactChecker:
    - FactChecker: Checks if facts are TRUE (uses tier filtering)
    - LLMOutputVerifier: Checks if LLM INTERPRETED sources correctly (no tier filtering)
    """

    def __init__(self, config):
        self.config = config

        # Use GPT-4o for verification (needs strong reasoning)
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=LLMVerificationResult)

        # ✅ Import prompts
        from prompts.llm_output_verification_prompts import get_llm_verification_prompts
        self.prompts = get_llm_verification_prompts()

        fact_logger.log_component_start("LLMOutputVerifier", model="gpt-4o")

    @traceable(
        name="verify_llm_interpretation",
        run_type="chain",
        tags=["llm-verification", "interpretation-check"]
    )
    async def verify_interpretation(
        self,
        claim: LLMClaim,  # ✅ Changed from Fact to LLMClaim
        excerpts_by_url: Dict[str, List[Dict]],
        scraped_content: Dict[str, str]
    ) -> LLMVerificationResult:
        """
        Verify if LLM accurately interpreted its cited source

        Args:
            claim: The LLMClaim object with the LLM's claim text
            excerpts_by_url: Excerpts extracted by Highlighter {url: [excerpts]}
            scraped_content: Full source content {url: content}

        Returns:
            LLMVerificationResult with verification assessment
        """
        start_time = time.time()

        fact_logger.logger.info(
            f"🔍 Verifying LLM interpretation for {claim.id}",
            extra={"claim_id": claim.id, "num_sources": len(excerpts_by_url)}
        )

        # ✅ Get the cited source from the claim
        cited_url = claim.cited_source

        if not cited_url or cited_url not in scraped_content:
            fact_logger.logger.warning(
                f"⚠️ Cited source not available for {claim.id}",
                extra={"claim_id": claim.id, "url": cited_url}
            )
            return self._create_error_result(claim, "Cited source not available")

        # Get excerpts and full content
        excerpts = excerpts_by_url.get(cited_url, [])
        full_content = scraped_content[cited_url]

        # Format excerpts for prompt
        excerpts_text = self._format_excerpts(excerpts)

        # Truncate full content if too long
        content_preview = full_content[:100000]
        if len(full_content) > 100000:
            content_preview += "\n\n[... content truncated ...]"

        # Call LLM for verification
        result = await self._verify_with_llm(
            claim,
            excerpts_text,
            content_preview
        )

        duration = time.time() - start_time
        fact_logger.log_component_complete(
            "LLMOutputVerifier",
            duration,
            claim_id=claim.id,
            verification_score=result.verification_score
        )

        return result

    def _format_excerpts(self, excerpts: List[Dict]) -> str:
        """Format excerpts for prompt"""
        if not excerpts:
            return "No excerpts found"

        formatted = []
        for i, ex in enumerate(excerpts, 1):
            formatted.append(
                f"EXCERPT #{i} (Relevance: {ex.get('relevance', 0):.2f}):\n"
                f"{ex.get('quote', '')}\n"
            )

        return "\n".join(formatted)

    @traceable(name="llm_verification_call", run_type="llm")
    async def _verify_with_llm(
        self,
        claim: LLMClaim,
        excerpts_text: str,
        source_content: str
    ) -> LLMVerificationResult:
        """Call LLM for verification"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompts["system"]),
            ("user", self.prompts["user"] + "\n\n{format_instructions}")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks(f"llm_verifier_{claim.id}")
        chain = prompt_with_format | self.llm | self.parser

        response = await chain.ainvoke(
            {
                "claim": claim.claim_text,  # ✅ Use claim_text
                "original_context": claim.context,  # ✅ Use context
                "excerpts": excerpts_text,
                "source_content": source_content
            },
            config={"callbacks": callbacks.handlers}
        )

        return LLMVerificationResult(
            claim_id=claim.id,
            claim_text=claim.claim_text,
            verification_score=response['verification_score'],
            assessment=response['assessment'],
            interpretation_issues=response.get('interpretation_issues', []),
            wording_comparison=response.get('wording_comparison', {}),
            confidence=response['confidence'],
            reasoning=response['reasoning']
        )

    def _create_error_result(self, claim: LLMClaim, error_msg: str) -> LLMVerificationResult:
        """Create error result when verification can't be performed"""
        return LLMVerificationResult(
            claim_id=claim.id,
            claim_text=claim.claim_text,
            verification_score=0.0,
            assessment=f"ERROR: {error_msg}",
            interpretation_issues=[error_msg],
            wording_comparison={},
            confidence=0.0,
            reasoning=f"Could not verify: {error_msg}"
        )