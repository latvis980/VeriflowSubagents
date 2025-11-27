# agents/llm_fact_extractor.py
"""
LLM Fact Extractor Agent
Extracts claim segments from LLM output for interpretation verification

KEY DIFFERENCES from FactExtractor:
- Preserves LLM's original wording (doesn't atomize claims)
- Maps each claim to its cited source URL
- Focuses on interpretation fidelity, not claim truth

USAGE: LLM Output Pipeline ONLY
"""

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List
import time

from prompts.llm_fact_extractor_prompts import get_llm_fact_extractor_prompts
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config


class LLMClaim(BaseModel):
    """A claim segment from LLM output with its cited sources"""
    id: str
    claim_text: str = Field(description="Original text from LLM output (preserved wording)")
    cited_sources: List[str] = Field(description="List of source URLs the LLM cited for this claim")  # Changed from cited_source
    context: str = Field(description="Surrounding context for checking cherry-picking")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence this is a factual claim")


class LLMFactExtractionOutput(BaseModel):
    """Output from LLM fact extraction"""
    claims: List[dict] = Field(description="List of claim segments with their sources")
    all_sources: List[str] = Field(description="All source URLs found in the output")


class LLMFactExtractor:
    """
    Extract claim segments from LLM output for interpretation verification
    
    Purpose: Identify what the LLM claimed and which source it cited
    NOT for atomizing claims or truth verification
    """

    def __init__(self, config):
        self.config = config

        # Use GPT-4o-mini for extraction
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=LLMFactExtractionOutput)

        # Load prompts from external file
        self.prompts = get_llm_fact_extractor_prompts()

        # Context window limits
        self.max_input_tokens = 100000  # GPT-4o-mini context limit
        self.tokens_per_char = 0.25
        self.max_input_chars = int(self.max_input_tokens / self.tokens_per_char)

        fact_logger.log_component_start("LLMFactExtractor", model="gpt-4o-mini")

    @traceable(
        name="extract_llm_claims",
        run_type="chain",
        tags=["llm-extraction", "interpretation-verification"]
    )
    async def extract_claims(self, parsed_content: dict) -> tuple[List[LLMClaim], List[str]]:
        """
        Extract claim segments from LLM output
        
        Args:
            parsed_content: Parsed HTML with text and links
            
        Returns:
            (list of LLMClaim objects, list of all source URLs)
        """
        start_time = time.time()

        fact_logger.logger.info(
            "🔍 Starting LLM claim extraction",
            extra={
                "text_length": len(parsed_content['text']),
                "num_sources": len(parsed_content['links']),
                "format": parsed_content.get('format', 'unknown')
            }
        )

        try:
            text_length = len(parsed_content['text'])

            if text_length > self.max_input_chars:
                fact_logger.logger.info(
                    f"📄 Large content detected ({text_length} chars), using chunking",
                    extra={"text_length": text_length, "max_chars": self.max_input_chars}
                )
                claims, all_sources = await self._extract_with_chunking(parsed_content)
            else:
                claims, all_sources = await self._extract_single_pass(parsed_content)

            duration = time.time() - start_time
            fact_logger.log_component_complete(
                "LLMFactExtractor",
                duration,
                num_claims=len(claims),
                total_sources=len(all_sources)
            )

            return claims, all_sources

        except Exception as e:
            fact_logger.log_component_error("LLMFactExtractor", e)
            raise

    async def _extract_single_pass(self, parsed_content: dict) -> tuple[List[LLMClaim], List[str]]:
        """Extract claims from content that fits in one context window"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", self.prompts["system"] + "\n\nIMPORTANT: You MUST return valid JSON only."),
            ("user", self.prompts["user"] + "\n\n{format_instructions}\n\nExtract claims now.")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks("llm_fact_extractor")
        chain = prompt_with_format | self.llm | self.parser

        fact_logger.logger.debug("🔗 Invoking LangChain for LLM claim extraction")

        try:
            response = await chain.ainvoke(
                {
                    "llm_output": parsed_content['text'],
                    "source_links": self._format_sources(parsed_content['links'])
                },
                config={"callbacks": callbacks.handlers}
            )

            return self._process_response(response, parsed_content)

        except Exception as e:
            fact_logger.logger.error(f"❌ LLM invocation failed: {e}")
            import traceback
            fact_logger.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def _extract_with_chunking(self, parsed_content: dict) -> tuple[List[LLMClaim], List[str]]:
        """Extract claims from large content by splitting into chunks"""

        text = parsed_content['text']
        chunk_size = self.max_input_chars - 1000  # Reserve space for prompts

        chunks = self._split_into_chunks(text, chunk_size)

        fact_logger.logger.info(
            f"📄 Split content into {len(chunks)} chunks",
            extra={"num_chunks": len(chunks)}
        )

        all_claims = []

        for i, chunk in enumerate(chunks, 1):
            fact_logger.logger.debug(f"🔍 Analyzing chunk {i}/{len(chunks)}")

            chunk_parsed = {
                'text': chunk,
                'links': parsed_content['links'],
                'format': parsed_content.get('format', 'unknown')
            }

            claims, _ = await self._extract_single_pass(chunk_parsed)
            all_claims.extend(claims)

        # Deduplicate claims
        unique_claims = self._deduplicate_claims(all_claims)

        all_sources = [link['url'] for link in parsed_content['links']]

        fact_logger.logger.info(
            f"✅ Chunking complete: {len(unique_claims)} unique claims from {len(all_claims)} total"
        )

        return unique_claims, all_sources

    def _process_response(self, response: dict, parsed_content: dict) -> tuple[List[LLMClaim], List[str]]:
        claims = []
        for i, claim_data in enumerate(response.get('claims', [])):
            try:
                # Handle both old format (cited_source) and new format (cited_sources)
                cited_sources = claim_data.get('cited_sources')
                if not cited_sources:
                    # Fallback for old format
                    single_source = claim_data.get('cited_source')
                    cited_sources = [single_source] if single_source else []

                claim = LLMClaim(
                    id=f"claim{i+1}",
                    claim_text=claim_data['claim_text'],
                    cited_sources=cited_sources,  # Now a list
                    context=claim_data.get('context', ''),
                    confidence=claim_data.get('confidence', 1.0)
                )
                claims.append(claim)

                fact_logger.logger.debug(
                    f"📝 Extracted claim {claim.id}",
                    extra={
                        "claim_id": claim.id,
                        "claim_text": claim.claim_text[:100],
                        "num_cited_sources": len(claim.cited_sources),  # ✅ New: log count
                        "cited_sources": claim.cited_sources  # ✅ New: log the list
                    }
                )
            except KeyError as e:
                fact_logger.logger.error(f"❌ Missing required field in claim_data: {e}")
                continue

        # Get all source URLs
        all_sources = response.get('all_sources', [])
        if not all_sources:
            all_sources = [link['url'] for link in parsed_content['links']]

        return claims, all_sources

    def _format_sources(self, links: List[dict]) -> str:
        """Format source links for the prompt"""
        return "\n".join([f"[{i+1}] {link['url']}" for i, link in enumerate(links)])

    def _split_into_chunks(self, text: str, chunk_size: int) -> List[str]:
        """Split text into overlapping chunks at sentence boundaries"""

        if len(text) <= chunk_size:
            return [text]

        chunks = []
        overlap = 500  # Characters of overlap
        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))

            # Try to find sentence boundary
            if end < len(text):
                boundary_search = text[max(0, end-200):end]
                sentence_endings = ['. ', '! ', '? ', '\n\n']

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

            start = max(start + 1, end - overlap)

            if end >= len(text):
                break

        return chunks

    def _deduplicate_claims(self, claims: List[LLMClaim]) -> List[LLMClaim]:
        """Remove duplicate claims based on text similarity"""
        unique_claims = []
        seen_texts = set()

        for claim in claims:
            claim_key = claim.claim_text.lower().strip()

            if claim_key not in seen_texts:
                seen_texts.add(claim_key)
                unique_claims.append(claim)

        # Re-number claims
        for i, claim in enumerate(unique_claims):
            claim.id = f"claim{i+1}"

        return unique_claims
