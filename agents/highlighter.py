# agents/highlighter.py
"""
OPTIMIZED Highlighter with Maximum Context Window for GPT-4o

KEY OPTIMIZATION: Increased from 50,000 to 400,000 characters
GPT-4o can handle 128K tokens (~500K characters), so we use 400K to leave room for prompts
"""
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import time

from utils.langsmith_config import langsmith_config
from utils.logger import fact_logger
from agents.fact_extractor import Fact
from prompts.highlighter_prompts import get_highlighter_prompts

class HighlighterOutput(BaseModel):
    excerpts: List[Dict[str, Any]] = Field(description="List of relevant excerpts with entities_matched")

class Highlighter:
    """Extract relevant excerpts with LangSmith tracing and MAXIMUM context for GPT-4o"""

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
            approx_max_tokens=self.max_content_tokens
        )

    @traceable(
        name="highlight_excerpts",
        run_type="chain",
        tags=["excerpt-extraction", "highlighter", "semantic", "large-context"]
    )
    async def highlight(self, fact: Fact, scraped_content: dict) -> dict:
        """
        Find excerpts that mention or support the fact using semantic understanding
        NOW WITH 8X MORE CONTEXT: 400K characters instead of 50K

        Returns: {url: [excerpts]}
        """
        start_time = time.time()
        results = {}

        fact_logger.logger.info(
            f"🔦 Highlighting excerpts for {fact.id} (LARGE CONTEXT MODE)",
            extra={
                "fact_id": fact.id,
                "statement": fact.statement[:100],
                "num_sources": len(scraped_content),
                "max_chars": self.max_content_chars
            }
        )

        # Global approach: check fact against ALL scraped sources
        for url in scraped_content.keys():
            if url not in scraped_content or not scraped_content[url]:
                fact_logger.logger.warning(
                    f"⚠️ Source not found or empty: {url}",
                    extra={"fact_id": fact.id, "url": url}
                )
                continue

            content = scraped_content[url]

            try:
                excerpts = await self._extract_excerpts(fact, url, content)
                results[url] = excerpts

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

            except Exception as e:
                fact_logger.logger.error(
                    f"❌ Failed to extract excerpts from {url}: {e}",
                    extra={"fact_id": fact.id, "url": url, "error": str(e)}
                )
                results[url] = []

        duration = time.time() - start_time
        total_excerpts = sum(len(excerpts) for excerpts in results.values())

        fact_logger.log_component_complete(
            "Highlighter",
            duration,
            fact_id=fact.id,
            total_excerpts=total_excerpts,
            sources_processed=len(results)
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