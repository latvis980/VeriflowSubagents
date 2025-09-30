# analyzer.py
"""
Improved Fact Analyzer - Global Source Checking Approach
Instead of mapping individual facts to specific sources, this approach:
1. Extracts all facts from the content
2. Scrapes ALL mentioned sources once
3. Checks each fact against the combined source content
"""

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List
import time

class Fact(BaseModel):
    id: str
    statement: str
    original_text: str
    confidence: float
    # Remove sources field - will be handled globally

class AnalyzerOutput(BaseModel):
    facts: List[dict] = Field(description="List of extracted facts")
    all_sources: List[str] = Field(description="All source URLs mentioned in the content")

class FactAnalyzer:
    """Extract factual claims without source mapping - check all facts against all sources"""

    def __init__(self, config):
        self.config = config
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=AnalyzerOutput)

    @traceable(name="analyze_facts_global", run_type="chain")
    async def analyze(self, parsed_content: dict) -> tuple[List[Fact], List[str]]:
        """
        Extract facts and return all source URLs separately
        Returns: (facts_list, all_source_urls)
        """

        system_prompt = """You are a fact extraction expert. Extract ALL factual claims from the content without trying to map them to specific sources.

WHAT TO EXTRACT:
- Specific dates, numbers, statistics, measurements
- Names of people, places, organizations  
- Historical events and their details
- Claims about products, services, features
- Comparisons and rankings
- Statements about cause and effect
- Definitive statements presented as facts

WHAT TO IGNORE:
- Opinions and subjective statements
- Predictions about the future
- Rhetorical questions
- General advice or recommendations
- Vague statements without specifics

IMPORTANT: Extract facts independently of their sources. The source verification will happen separately.

Return ONLY valid JSON in this exact format:
{
  "facts": [
    {
      "statement": "The hotel opened in March 2017",
      "original_text": "The Silo Hotel opened in March 2017",
      "confidence": 0.95
    }
  ],
  "all_sources": ["https://source1.com", "https://source2.com"]
}"""

        user_prompt = """Extract all factual claims from the following content.

TEXT TO ANALYZE:
{text}

AVAILABLE SOURCE URLS:
{sources}

INSTRUCTIONS:
- Find every verifiable factual claim in the text
- Extract facts without worrying about which source supports them
- Be thorough - don't miss any facts
- Keep statements precise and atomic
- List all source URLs separately
- Return valid JSON only

{format_instructions}

Extract all factual claims now."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", user_prompt)
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        chain = prompt_with_format | self.llm | self.parser

        response = await chain.ainvoke({
            "text": parsed_content['text'],
            "sources": self._format_sources(parsed_content['links'])
        })

        # Convert to Fact objects
        facts = []
        for i, fact_data in enumerate(response.get('facts', [])):
            fact = Fact(
                id=f"fact{i+1}",
                statement=fact_data['statement'],
                original_text=fact_data.get('original_text', ''),
                confidence=fact_data.get('confidence', 1.0)
            )
            facts.append(fact)

        # Get all source URLs
        all_sources = response.get('all_sources', [])

        return facts, all_sources

    def _format_sources(self, links: List[dict]) -> str:
        """Format source links for the prompt"""
        return "\n".join([f"- {link['url']}" for link in links])