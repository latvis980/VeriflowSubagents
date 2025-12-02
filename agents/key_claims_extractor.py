# agents/key_claims_extractor.py
"""
Key Claims Extractor Agent
Extracts ONLY the 2-3 central thesis claims from text

KEY DIFFERENCES from FactAnalyzer:
- Extracts 2-3 KEY CLAIMS only (not all verifiable facts)
- Focuses on THESIS statements, not supporting evidence
- Identifies what the author is trying to PROVE

USAGE: Key Claims Pipeline
- For finding the main arguments an article is built around
- These are claims that supporting facts are meant to prove
"""

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langsmith import traceable
from pydantic import BaseModel, Field
from typing import List, Optional
import time

from prompts.key_claims_extractor_prompts import get_key_claims_prompts
from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config


class KeyClaim(BaseModel):
    """A key claim (central thesis) from the text"""
    id: str
    statement: str
    sources: List[str]  # Will be empty for plain text
    original_text: str
    confidence: float


class ContentLocation(BaseModel):
    """Geographic and language context for the content"""
    country: str = Field(default="international", description="Primary country where events take place")
    country_code: str = Field(default="", description="ISO 2-letter country code")
    language: str = Field(default="english", description="Primary language for that country")
    confidence: float = Field(default=0.5, description="Confidence in location detection")


class KeyClaimsOutput(BaseModel):
    """Output from key claims extraction"""
    facts: List[dict] = Field(description="List of 2-3 key claims")
    all_sources: List[str] = Field(description="All source URLs mentioned")
    content_location: Optional[dict] = Field(default=None, description="Country and language info")


class KeyClaimsResult(BaseModel):
    """Complete result from key claims extraction including location context"""
    claims: List[KeyClaim]
    all_sources: List[str]
    content_location: ContentLocation


class KeyClaimsExtractor:
    """
    Extract ONLY the 2-3 key claims (central thesis) from text
    
    Unlike FactAnalyzer which extracts ALL verifiable facts,
    this extracts only the main arguments the text is trying to prove.
    """

    def __init__(self, config):
        self.config = config

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser(pydantic_object=KeyClaimsOutput)
        self.prompts = get_key_claims_prompts()

        # Large file support
        self.max_input_chars = 100000  # ~25k tokens

        fact_logger.log_component_start(
            "KeyClaimsExtractor",
            model="gpt-4o-mini",
            max_claims=3
        )

    @traceable(name="key_claims_extraction")
    async def extract(self, parsed_content: dict) -> tuple[List[KeyClaim], List[str], ContentLocation]:
        """
        Extract 2-3 key claims from parsed content
        
        Args:
            parsed_content: Dict with 'text', 'links', 'format' keys
            
        Returns:
            Tuple of (key_claims, all_sources, content_location)
        """
        start_time = time.time()

        text_length = len(parsed_content.get('text', ''))
        fact_logger.logger.info(
            f"🎯 Starting key claims extraction",
            extra={
                "text_length": text_length,
                "num_links": len(parsed_content.get('links', []))
            }
        )

        # Check if we need chunking (for very large files)
        if text_length > self.max_input_chars:
            fact_logger.logger.info(f"📄 Large content detected ({text_length} chars), using chunked extraction")
            claims, sources, location = await self._extract_with_chunking(parsed_content)
        else:
            claims, sources, location = await self._extract_single_pass(parsed_content)

        duration = time.time() - start_time
        fact_logger.logger.info(
            f"✅ Key claims extraction complete",
            extra={
                "num_claims": len(claims),
                "duration_seconds": round(duration, 2),
                "country": location.country,
                "language": location.language
            }
        )

        return claims, sources, location

    async def _extract_single_pass(self, parsed_content: dict) -> tuple[List[KeyClaim], List[str], ContentLocation]:
        """Extract key claims in a single LLM call"""

        system_prompt = self.prompts["system"]
        user_prompt = self.prompts["user"]

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No other text."),
            ("user", user_prompt + "\n\n{format_instructions}\n\nReturn your response as valid JSON.")
        ])

        prompt_with_format = prompt.partial(
            format_instructions=self.parser.get_format_instructions()
        )

        callbacks = langsmith_config.get_callbacks("key_claims_extractor")
        chain = prompt_with_format | self.llm | self.parser

        fact_logger.logger.debug("🔗 Invoking LangChain for key claims extraction")

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
            import traceback
            fact_logger.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def _extract_with_chunking(self, parsed_content: dict) -> tuple[List[KeyClaim], List[str], ContentLocation]:
        """Extract key claims from large content by splitting into chunks"""

        text = parsed_content['text']
        chunk_size = self.max_input_chars - 10000  # Reserve space for prompts

        chunks = self._split_into_chunks(text, chunk_size)

        fact_logger.logger.info(
            f"📄 Split content into {len(chunks)} chunks",
            extra={"num_chunks": len(chunks)}
        )

        all_claims = []
        all_location_votes = []

        for i, chunk in enumerate(chunks, 1):
            fact_logger.logger.debug(f"🔍 Analyzing chunk {i}/{len(chunks)}")

            chunk_parsed = {
                'text': chunk,
                'links': parsed_content['links'],
                'format': parsed_content.get('format', 'unknown')
            }

            chunk_claims, _, chunk_location = await self._extract_single_pass(chunk_parsed)
            all_claims.extend(chunk_claims)
            all_location_votes.append(chunk_location)

        # For key claims, we want to deduplicate and keep only the top 2-3
        unique_claims = self._deduplicate_and_rank_claims(all_claims)

        # Get all sources from parsed content
        all_sources = [link['url'] for link in parsed_content['links']]

        # Aggregate location votes
        content_location = self._aggregate_location_votes(all_location_votes)

        return unique_claims, all_sources, content_location

    def _split_into_chunks(self, text: str, chunk_size: int) -> List[str]:
        """Split text into chunks, trying to break at paragraph boundaries"""
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        current_pos = 0

        while current_pos < len(text):
            end_pos = min(current_pos + chunk_size, len(text))

            if end_pos < len(text):
                # Try to find a paragraph break
                para_break = text.rfind('\n\n', current_pos, end_pos)
                if para_break > current_pos + chunk_size // 2:
                    end_pos = para_break + 2

            chunks.append(text[current_pos:end_pos])
            current_pos = end_pos

        return chunks

    def _process_response(self, response: dict, parsed_content: dict) -> tuple[List[KeyClaim], List[str], ContentLocation]:
        """Process LLM response into structured output"""

        claims = []
        raw_claims = response.get('facts', [])

        # Limit to 3 claims maximum
        for i, claim_data in enumerate(raw_claims[:3], 1):
            claim = KeyClaim(
                id=claim_data.get('id', f'KC{i}'),
                statement=claim_data.get('statement', ''),
                sources=claim_data.get('sources', []),
                original_text=claim_data.get('original_text', ''),
                confidence=float(claim_data.get('confidence', 0.8))
            )
            claims.append(claim)

        # Extract sources
        all_sources = response.get('all_sources', [])

        # Extract location
        location_data = response.get('content_location', {})
        content_location = ContentLocation(
            country=location_data.get('country', 'international'),
            country_code=location_data.get('country_code', ''),
            language=location_data.get('language', 'english'),
            confidence=float(location_data.get('confidence', 0.5))
        )

        return claims, all_sources, content_location

    def _deduplicate_and_rank_claims(self, claims: List[KeyClaim]) -> List[KeyClaim]:
        """Deduplicate claims and keep top 3 by confidence"""
        seen_statements = set()
        unique_claims = []

        for claim in claims:
            # Normalize for comparison
            normalized = claim.statement.lower().strip()
            if normalized not in seen_statements:
                seen_statements.add(normalized)
                unique_claims.append(claim)

        # Sort by confidence and take top 3
        unique_claims.sort(key=lambda x: x.confidence, reverse=True)
        return unique_claims[:3]

    def _aggregate_location_votes(self, votes: List[ContentLocation]) -> ContentLocation:
        """Aggregate location votes from multiple chunks"""
        if not votes:
            return ContentLocation()

        # Find most common country
        country_counts = {}
        for vote in votes:
            key = (vote.country, vote.language)
            if key not in country_counts:
                country_counts[key] = {'count': 0, 'confidence': 0, 'code': vote.country_code}
            country_counts[key]['count'] += 1
            country_counts[key]['confidence'] = max(country_counts[key]['confidence'], vote.confidence)

        # Get the most common
        best_key = max(country_counts.keys(), key=lambda k: (country_counts[k]['count'], country_counts[k]['confidence']))

        return ContentLocation(
            country=best_key[0],
            country_code=country_counts[best_key]['code'],
            language=best_key[1],
            confidence=country_counts[best_key]['confidence']
        )

    def _format_sources(self, links: list) -> str:
        """Format source links for the prompt"""
        if not links:
            return "No source links provided"

        formatted = []
        for i, link in enumerate(links, 1):
            url = link.get('url', 'Unknown URL')
            text = link.get('text', '')[:100]
            formatted.append(f"[{i}] {url}")
            if text:
                formatted.append(f"    Text: {text}")

        return "\n".join(formatted)
