# agents/highlighter.py
"""
OPTIMIZED Highlighter with Maximum Context Window for GPT-4o

KEY OPTIMIZATIONS:
1. Increased from 50,000 to 400,000 characters for GPT-4o's 128K token window
2. ✅ PARALLEL PROCESSING: All sources processed simultaneously using asyncio.gather()
   - Previously: Sequential loop (5 sources = 5 sequential LLM calls)
   - Now: All sources processed in parallel (5 sources = 1 parallel batch)
   - ~60-70% faster for multiple sources
"""
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Tuple
import time
import asyncio

from utils.langsmith_config import langsmith_config
from utils.logger import fact_logger
from agents.fact_extractor import Fact
from prompts.highlighter_prompts import get_highlighter_prompts


class HighlighterOutput(BaseModel):
    excerpts: List[Dict[str, Any]] = Field(description="List of relevant excerpts with entities_matched")


class Highlighter:
    """Extract relevant excerpts with LangSmith tracing and MAXIMUM context for GPT-4o

    ✅ OPTIMIZED: Parallel processing for all sources using asyncio.gather()
    """

    def __init__(self, config):
        self.config = config

        # ✅ PROPER JSON MODE - OpenAI guarantees valid JSON
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        # ✅ SIMPLE PARSER - No fixing needed
        self.parser = JsonOutputParser(pydantic_object=HighlighterOutput)

        # Load prompts during initialization
        self.prompts = get_highlighter_prompts()

        # ✅ OPTIMIZED: Use most of GPT-4o's context window
        # GPT-4o: 128K tokens ≈ 512K characters
        # Using 400K leaves ~25K tokens for prompts, responses, and safety margin
        self.max_content_chars = 400000  # 8x increase from 50K!

        # Calculate approximate token usage
        self.approx_tokens_per_char = 0.25  # 1 token ≈ 4 chars
        self.max_content_tokens = int(self.max_content_chars * self.approx_tokens_per_char)

        fact_logger.log_component_start(
            "Highlighter", 
            model="gpt-4o",
            max_context_chars=self.max_content_chars,
            approx_max_tokens=self.max_content_tokens,
            parallel_processing=True  # ✅ NEW: Indicate parallel mode
        )

    @traceable(
        name="highlight_excerpts",
        run_type="chain",
        tags=["excerpt-extraction", "highlighter", "semantic", "large-context", "parallel"]
    )
    async def highlight(self, fact: Fact, scraped_content: dict) -> dict:
        """
        Find excerpts that mention or support the fact using semantic understanding

        ✅ OPTIMIZED: All sources processed in PARALLEL using asyncio.gather()
        - Previously: Sequential for loop (slow)
        - Now: All LLM calls run simultaneously (fast)

        Returns: {url: [excerpts]}
        """
        start_time = time.time()
        results = {}

        fact_logger.logger.info(
            f"🔦 Highlighting excerpts for {fact.id} (PARALLEL MODE)",
            extra={
                "fact_id": fact.id,
                "statement": fact.statement[:100],
                "num_sources": len(scraped_content),
                "max_chars": self.max_content_chars,
                "processing_mode": "parallel"
            }
        )

        # ✅ STEP 1: Filter valid sources and prepare for parallel processing
        valid_sources: List[Tuple[str, str]] = []

        for url, content in scraped_content.items():
            if not content:
                fact_logger.logger.warning(
                    f"⚠️ Source not found or empty: {url}",
                    extra={"fact_id": fact.id, "url": url}
                )
                results[url] = []  # Empty result for invalid sources
                continue
            valid_sources.append((url, content))

        if not valid_sources:
            fact_logger.logger.warning(
                f"⚠️ No valid sources to highlight for {fact.id}",
                extra={"fact_id": fact.id}
            )
            return results

        # ✅ STEP 2: Create parallel extraction tasks for ALL valid sources
        fact_logger.logger.info(
            f"🚀 Starting PARALLEL excerpt extraction for {len(valid_sources)} sources",
            extra={
                "fact_id": fact.id,
                "num_sources": len(valid_sources),
                "urls": [url for url, _ in valid_sources]
            }
        )

        async def extract_with_error_handling(url: str, content: str) -> Tuple[str, List]:
            """Wrapper to handle errors and return (url, excerpts) tuple"""
            try:
                excerpts = await self._extract_excerpts(fact, url, content)
                fact_logger.logger.debug(
                    f"✂️ Found {len(excerpts)} excerpts from {url}",
                    extra={
                        "fact_id": fact.id,
                        "url": url,
                        "num_excerpts": len(excerpts),
                        "content_length_used": min(len(content), self.max_content_chars),
                        "truncated": len(content) > self.max_content_chars
                    }
                )
                return (url, excerpts)
            except Exception as e:
                fact_logger.logger.error(
                    f"❌ Failed to extract excerpts from {url}: {e}",
                    extra={"fact_id": fact.id, "url": url, "error": str(e)}
                )
                return (url, [])

        # ✅ STEP 3: Execute ALL extractions in PARALLEL
        tasks = [
            extract_with_error_handling(url, content) 
            for url, content in valid_sources
        ]

        parallel_start = time.time()
        extraction_results = await asyncio.gather(*tasks, return_exceptions=True)
        parallel_duration = time.time() - parallel_start

        # ✅ STEP 4: Process results
        for result in extraction_results:
            if isinstance(result, Exception):
                fact_logger.logger.error(
                    f"❌ Unexpected error in parallel extraction: {result}",
                    extra={"fact_id": fact.id, "error": str(result)}
                )
                continue

            url, excerpts = result
            results[url] = excerpts

        # ✅ STEP 5: Log completion metrics
        duration = time.time() - start_time
        total_excerpts = sum(len(excerpts) for excerpts in results.values())

        # Calculate estimated sequential time for comparison
        # Average ~3-5 seconds per LLM call
        estimated_sequential_time = len(valid_sources) * 4  # Conservative estimate
        time_saved = max(0, estimated_sequential_time - duration)
        speedup_percent = (time_saved / estimated_sequential_time * 100) if estimated_sequential_time > 0 else 0

        fact_logger.logger.info(
            f"⚡ Parallel highlighting complete",
            extra={
                "fact_id": fact.id,
                "total_duration_sec": round(duration, 2),
                "parallel_batch_duration_sec": round(parallel_duration, 2),
                "num_sources": len(valid_sources),
                "total_excerpts": total_excerpts,
                "estimated_sequential_time_sec": estimated_sequential_time,
                "estimated_time_saved_sec": round(time_saved, 2),
                "estimated_speedup_percent": round(speedup_percent, 1)
            }
        )

        fact_logger.log_component_complete(
            "Highlighter",
            duration,
            fact_id=fact.id,
            total_excerpts=total_excerpts,
            sources_processed=len(results),
            processing_mode="parallel"
        )

        return results

    @traceable(name="extract_single_excerpt", run_type="llm")
    async def _extract_excerpts(self, fact: Fact, url: str, content: str) -> list:
        """
        Extract excerpts from a single source using semantic understanding

        ✅ OPTIMIZED: Now uses 400K chars instead of 50K (8x increase!)
        This means most articles will NOT be truncated
        """

        # ✅ INCREASED CONTEXT: Use much more content for better matching
        content_to_analyze = content[:self.max_content_chars]

        original_length = len(content)
        truncated = original_length > self.max_content_chars

        # Calculate how much we're using
        usage_percent = (len(content_to_analyze) / original_length * 100) if original_length > 0 else 0

        # Log truncation with more detail
        if truncated:
            chars_lost = original_length - self.max_content_chars
            fact_logger.logger.warning(
                f"⚠️ Content truncated for analysis",
                extra={
                    "fact_id": fact.id,
                    "url": url,
                    "original_length": original_length,
                    "used_length": self.max_content_chars,
                    "chars_lost": chars_lost,
                    "usage_percent": round(usage_percent, 1)
                }
            )
        else:
            fact_logger.logger.info(
                f"✅ Using full content (no truncation needed)",
                extra={
                    "fact_id": fact.id,
                    "url": url,
                    "content_length": original_length,
                    "usage_percent": 100.0
                }
            )

        # ✅ CLEAN PROMPT USAGE
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompts["system"]),
            ("user", self.prompts["user"])
        ])

        # ✅ FORMAT INSTRUCTIONS
        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks(f"highlighter_{fact.id}")

        # ✅ CLEAN CHAIN - No manual JSON parsing needed
        chain = prompt_with_format | self.llm | self.parser

        fact_logger.logger.debug(
            f"🔍 Analyzing {len(content_to_analyze):,} chars for excerpts",
            extra={
                "fact_id": fact.id,
                "url": url,
                "content_length": len(content_to_analyze),
                "approx_tokens": int(len(content_to_analyze) * self.approx_tokens_per_char)
            }
        )

        response = await chain.ainvoke(
            {
                "fact": fact.statement,
                "url": url,
                "content": content_to_analyze  # ✅ USING 400K CHARS NOW (8X MORE!)
            },
            config={"callbacks": callbacks.handlers}
        )

        # ✅ DIRECT DICT ACCESS - Parser returns clean dict
        excerpts = response.get('excerpts', [])

        fact_logger.logger.debug(
            f"📊 Extracted {len(excerpts)} excerpts",
            extra={
                "fact_id": fact.id,
                "url": url,
                "num_excerpts": len(excerpts)
            }
        )

        return excerpts