# agents/highlighter.py
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langsmith import traceable
import time
from typing import Dict, List

# Fixed imports
from utils.langsmith_config import langsmith_config
from utils.logger import fact_logger
from agents.analyser import Fact
from prompts.highlighter_prompts import get_highlighter_prompts

class Highlighter:
    """Extract relevant excerpts with LangSmith tracing"""

    def __init__(self, config):
        self.config = config
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0
        )

        # Load prompts
        self.prompts = get_highlighter_prompts()

        fact_logger.log_component_start("Highlighter", model="gpt-4o-mini")

    @traceable(
        name="highlight_excerpts",
        run_type="chain",
        tags=["excerpt-extraction", "highlighter"]
    )
    async def highlight(self, fact: Fact, scraped_content: Dict[str, str]) -> Dict[str, List[Dict]]:
        """
        Find excerpts that mention or support the fact
        Returns: {url: [excerpts]}
        """
        start_time = time.time()
        results = {}

        fact_logger.logger.info(
            f"🔦 Highlighting excerpts for {fact.id}",
            extra={
                "fact_id": fact.id,
                "statement": fact.statement[:100],
                "num_sources": len(fact.sources)
            }
        )

        for url in fact.sources:
            if url not in scraped_content:
                fact_logger.logger.warning(
                    f"⚠️ Source not found in scraped content: {url}",
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
                        "num_excerpts": len(excerpts)
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
    async def _extract_excerpts(self, fact: Fact, url: str, content: str) -> List[Dict]:
        """Extract excerpts from a single source"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompts["system"]),
            ("user", self.prompts["user"])
        ])

        callbacks = langsmith_config.get_callbacks(f"highlighter_{fact.id}")
        chain = prompt | self.llm

        result = await chain.ainvoke(
            {
                "fact": fact.statement,
                "url": url,
                "content": content[:8000]
            },
            config={"callbacks": callbacks.handlers}
        )

        import json
        data = json.loads(result.content)
        return data.get('excerpts', [])