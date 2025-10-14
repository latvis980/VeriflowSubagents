# agents/analyser.py
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
    sources: List[str]  # Will be empty in global approach
    original_text: str
    confidence: float

class GlobalAnalyzerOutput(BaseModel):
    facts: List[dict] = Field(description="List of extracted facts")
    all_sources: List[str] = Field(description="All source URLs mentioned")

class FactAnalyzer:
    """Extract factual claims with global source checking and large file support"""

    def __init__(self, config):
        self.config = config

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=GlobalAnalyzerOutput)

        # Load prompts from external file
        self.prompts = get_analyzer_prompts()

        # Context window limits (conservative estimates)
        self.max_input_tokens = 100000  # GPT-4o-mini context limit
        self.tokens_per_char = 0.25     # Rough estimate: 4 chars per token
        self.max_input_chars = int(self.max_input_tokens / self.tokens_per_char)

        fact_logger.log_component_start("FactAnalyzer", model="gpt-4o-mini")

    @traceable(
        name="analyze_facts",
        run_type="chain",
        tags=["fact-extraction", "analyzer", "global-approach"]
    )
    async def analyze(self, parsed_content: dict) -> tuple[List[Fact], List[str]]:
        """
        Extract facts and return all source URLs separately (GLOBAL APPROACH with chunking)
        Returns: (facts_list, all_source_urls)
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
            # Check if content fits in context window
            text_length = len(parsed_content['text'])

            if text_length > self.max_input_chars:
                fact_logger.logger.info(
                    f"📄 Large content detected ({text_length} chars), using chunking approach",
                    extra={"text_length": text_length, "max_chars": self.max_input_chars}
                )
                facts, all_sources = await self._analyze_with_chunking(parsed_content)
            else:
                facts, all_sources = await self._analyze_single_pass(parsed_content)

            duration = time.time() - start_time
            fact_logger.log_component_complete(
                "FactAnalyzer",
                duration,
                num_facts=len(facts),
                total_sources=len(all_sources),
                approach="global"
            )

            return facts, all_sources

        except Exception as e:
            fact_logger.log_component_error("FactAnalyzer", e)
            raise

    async def _analyze_single_pass(self, parsed_content: dict) -> tuple[List[Fact], List[str]]:
        """Analyze content that fits in a single context window"""

        # Use prompts from external file, modified for global approach
        system_prompt = self.prompts["system"].replace(
            "Map it to the source URL(s) that supposedly support it",
            "Note: Source verification will happen globally across all sources"
        ).replace(
            "Match facts to ALL relevant source URLs mentioned nearby",
            "Focus on extracting verifiable facts, not mapping to specific sources"
        )

        user_prompt = self.prompts["user"].replace(
            "Match each fact to its supporting source URL(s)",
            "Extract facts without mapping to specific sources"
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + "\n\nIMPORTANT: You MUST return valid JSON only. No other text."),
            ("user", user_prompt + "\n\n{format_instructions}\n\nReturn your response as valid JSON.")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks("fact_analyzer")
        chain = prompt_with_format | self.llm | self.parser

        fact_logger.logger.debug("🔗 Invoking LangChain with global approach (single pass)")

        try:
            response = await chain.ainvoke(
                {
                    "text": parsed_content['text'],
                    "sources": self._format_sources(parsed_content['links'])
                },
                config={"callbacks": callbacks.handlers}
            )

            return self._process_response(response, parsed_content)

        except Exception as e:
            fact_logger.logger.error(f"❌ LLM invocation failed: {e}")
            # Log the actual error for debugging
            import traceback
            fact_logger.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def _analyze_with_chunking(self, parsed_content: dict) -> tuple[List[Fact], List[str]]:
        """Analyze large content by splitting into chunks"""

        text = parsed_content['text']
        chunk_size = self.max_input_chars - 2000  # Leave room for prompts and sources

        # Split text into chunks with overlap to avoid losing facts at boundaries
        overlap = 500
        chunks = self._create_overlapping_chunks(text, chunk_size, overlap)

        fact_logger.logger.info(
            f"📄 Processing {len(chunks)} chunks",
            extra={"num_chunks": len(chunks), "chunk_size": chunk_size}
        )

        all_facts = []
        all_sources = set()

        for i, chunk in enumerate(chunks):
            fact_logger.logger.debug(f"Processing chunk {i+1}/{len(chunks)}")

            # Create temporary parsed_content for this chunk
            chunk_content = {
                'text': chunk,
                'links': parsed_content['links'],  # Keep all links for each chunk
                'format': parsed_content.get('format', 'unknown')
            }

            try:
                chunk_facts, chunk_sources = await self._analyze_single_pass(chunk_content)
                all_facts.extend(chunk_facts)
                all_sources.update(chunk_sources)

                fact_logger.logger.debug(
                    f"Chunk {i+1}: extracted {len(chunk_facts)} facts",
                    extra={"chunk": i+1, "facts": len(chunk_facts)}
                )

            except Exception as e:
                fact_logger.logger.warning(
                    f"Failed to process chunk {i+1}: {e}",
                    extra={"chunk": i+1, "error": str(e)}
                )

        # Deduplicate facts (same statement might appear in overlapping chunks)
        unique_facts = self._deduplicate_facts(all_facts)

        fact_logger.logger.info(
            f"🔄 Deduplication: {len(all_facts)} -> {len(unique_facts)} facts",
            extra={"original": len(all_facts), "deduplicated": len(unique_facts)}
        )

        return unique_facts, list(all_sources)

    def _create_overlapping_chunks(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Create overlapping text chunks to avoid losing facts at boundaries"""
        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # Try to end at a sentence boundary
            if end < len(text):
                # Look for sentence endings near the chunk boundary
                boundary_search = text[max(0, end-200):min(len(text), end+200)]
                sentence_endings = ['.', '!', '?', '\n\n']

                best_boundary = end
                for ending in sentence_endings:
                    pos = boundary_search.rfind(ending)
                    if pos != -1:
                        actual_pos = max(0, end-200) + pos + 1
                        if abs(actual_pos - end) < abs(best_boundary - end):
                            best_boundary = actual_pos

                end = min(best_boundary, len(text))

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Next chunk starts with overlap
            start = max(start + 1, end - overlap)

            if end >= len(text):
                break

        return chunks

    def _deduplicate_facts(self, facts: List[Fact]) -> List[Fact]:
        """Remove duplicate facts based on statement similarity"""
        unique_facts = []
        seen_statements = set()

        for fact in facts:
            # Simple deduplication based on statement text
            statement_key = fact.statement.lower().strip()

            if statement_key not in seen_statements:
                seen_statements.add(statement_key)
                unique_facts.append(fact)

        # Re-number the facts
        for i, fact in enumerate(unique_facts):
            fact.id = f"fact{i+1}"

        return unique_facts

    def _process_response(self, response: dict, parsed_content: dict) -> tuple[List[Fact], List[str]]:
        """Convert response to Fact objects and extract sources"""

        # ✅ CHECK FOR ERROR IN RESPONSE
        if 'error' in response:
            error_msg = response.get('error', 'Unknown error')
            fact_logger.logger.error(f"❌ LLM returned error: {error_msg}")
            raise ValueError(f"LLM error: {error_msg}")

        # ✅ ENSURE WE HAVE FACTS KEY
        if 'facts' not in response:
            fact_logger.logger.error(f"❌ Missing 'facts' in response: {response}")
            raise ValueError(f"Invalid response structure: missing 'facts' key. Got: {list(response.keys())}")

        # Convert to Fact objects (sources will be empty for global approach)
        facts = []
        for i, fact_data in enumerate(response.get('facts', [])):
            try:
                fact = Fact(
                    id=f"fact{i+1}",
                    statement=fact_data['statement'],
                    sources=[],  # Empty for global approach - sources handled separately
                    original_text=fact_data.get('original_text', ''),
                    confidence=fact_data.get('confidence', 1.0)
                )
                facts.append(fact)

                fact_logger.logger.debug(
                    f"📝 Extracted fact {fact.id}",
                    extra={
                        "fact_id": fact.id,
                        "statement": fact.statement[:100]
                    }
                )
            except KeyError as e:
                fact_logger.logger.error(f"❌ Missing required field in fact_data: {e}")
                continue

        # Get all source URLs
        all_sources = response.get('all_sources', [])
        if not all_sources:
            # Fallback: extract from parsed_content
            all_sources = [link['url'] for link in parsed_content['links']]

        return facts, all_sources

    def _format_sources(self, links: List[dict]) -> str:
        """Format source links for the prompt"""
        return "\n".join([f"- {link['url']}" for link in links])