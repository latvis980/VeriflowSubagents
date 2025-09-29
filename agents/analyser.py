# agents/analyzer.py
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List
import time
from prompts.analyzer_prompts import get_analyzer_prompts
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config

class Fact(BaseModel):
    id: str
    statement: str
    sources: List[str]
    original_text: str
    confidence: float

class AnalyzerOutput(BaseModel):
    facts: List[dict] = Field(description="List of extracted facts")

class FactAnalyzer:
    """Extract factual claims with LangSmith tracing"""

    def __init__(self, config):
        self.config = config

        # ✅ PROPER JSON MODE - OpenAI guarantees valid JSON
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        # ✅ SIMPLE PARSER - No fixing needed
        self.parser = JsonOutputParser(pydantic_object=AnalyzerOutput)

        # Load prompts during initialization
        self.prompts = get_analyzer_prompts()

        fact_logger.log_component_start("FactAnalyzer", model="gpt-4o-mini")

    @traceable(
        name="analyze_facts",
        run_type="chain",
        tags=["fact-extraction", "analyzer"]
    )
    async def analyze(self, parsed_content: dict) -> List[Fact]:
        """
        Extract facts with full LangSmith tracing
        """
        start_time = time.time()

        fact_logger.logger.info(
            "🔍 Starting fact analysis",
            extra={
                "text_length": len(parsed_content['text']),
                "num_sources": len(parsed_content['links']),
                "format": parsed_content.get('format', 'unknown')
            }
        )

        try:
            # ✅ EXPLICIT JSON MENTION
            system_prompt = self.prompts["system"] + "\n\nIMPORTANT: You MUST return valid JSON only. No other text."

            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("user", self.prompts["user"] + "\n\n{format_instructions}\n\nReturn your response as valid JSON.")
            ])

            # ✅ FORMAT INSTRUCTIONS
            prompt_with_format = prompt.partial(
                format_instructions=self.parser.get_format_instructions()
            )

            # Get callbacks for LangSmith
            callbacks = langsmith_config.get_callbacks("fact_analyzer")

            # ✅ CLEAN CHAIN - No manual JSON parsing needed
            chain = prompt_with_format | self.llm | self.parser

            fact_logger.logger.debug("🔗 Invoking LangChain with enforced JSON mode")

            response = await chain.ainvoke(
                {
                    "text": parsed_content['text'],
                    "sources": self._format_sources(parsed_content['links'])
                },
                config={"callbacks": callbacks.handlers}
            )

            # ✅ DIRECT DICT ACCESS - Parser returns clean dict
            facts_data = response

            # Convert to Fact objects
            facts = []
            for i, fact_data in enumerate(facts_data.get('facts', [])):
                fact = Fact(
                    id=f"fact{i+1}",
                    statement=fact_data['statement'],
                    sources=fact_data['sources'],
                    original_text=fact_data.get('original_text', ''),
                    confidence=fact_data.get('confidence', 1.0)
                )
                facts.append(fact)

                fact_logger.logger.debug(
                    f"📝 Extracted fact {fact.id}",
                    extra={
                        "fact_id": fact.id,
                        "statement": fact.statement[:100],
                        "num_sources": len(fact.sources)
                    }
                )

            duration = time.time() - start_time
            fact_logger.log_component_complete(
                "FactAnalyzer",
                duration,
                num_facts=len(facts),
                avg_sources_per_fact=sum(len(f.sources) for f in facts) / len(facts) if facts else 0
            )

            return facts

        except Exception as e:
            fact_logger.log_component_error("FactAnalyzer", e)
            raise

    def _format_sources(self, links: List[dict]) -> str:
        """Format source links for the prompt"""
        return "\n".join([f"- {link['url']}" for link in links])