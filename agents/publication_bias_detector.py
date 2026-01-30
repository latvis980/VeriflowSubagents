# agents/publication_bias_detector.py
"""
Publication Bias Detector with MBFC Integration + Supabase Storage
Identifies political leanings and biases of news sources using:
1. Supabase database cache (fastest)
2. Media Bias/Fact Check (MBFC) web lookup (primary source)
3. Local database (fallback)

UPDATED: Added country_freedom_rating field and Supabase integration
"""

from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from urllib.parse import urlparse
from datetime import datetime, timedelta
import asyncio
import re
import json

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

from utils.mbfc_scraper import MBFCScraper, MBFCExtractedData

from utils.logger import fact_logger


class PublicationProfile(BaseModel):
    """Profile of a publication's known biases"""
    name: str
    political_leaning: str  # "left", "center-left", "center", "center-right", "right"
    bias_rating: float  # 0-10 scale (internally normalized)
    ownership: Optional[str] = None
    target_audience: Optional[str] = None
    known_biases: List[str] = []
    credibility_notes: Optional[str] = None
    # MBFC-specific fields
    factual_reporting: Optional[str] = None
    credibility_rating: Optional[str] = None
    country_freedom_rating: Optional[str] = None  # NEW: Press freedom rating
    mbfc_url: Optional[str] = None
    failed_fact_checks: List[str] = []
    source: str = "local"  # "local", "mbfc", or "database"
    # Tier assignment
    assigned_tier: Optional[int] = None
    tier_reasoning: Optional[str] = None


class MBFCResult(BaseModel):
    """Structured result from MBFC lookup"""
    publication_name: str
    bias_rating: Optional[str] = None
    bias_score: Optional[float] = None
    factual_reporting: Optional[str] = None
    factual_score: Optional[float] = None
    credibility_rating: Optional[str] = None
    country_freedom_rating: Optional[str] = None  # NEW: MBFC press freedom rating
    country: Optional[str] = None
    media_type: Optional[str] = None
    traffic_popularity: Optional[str] = None
    ownership: Optional[str] = None
    funding: Optional[str] = None
    failed_fact_checks: List[str] = []
    summary: Optional[str] = None
    special_tags: List[str] = []
    mbfc_url: Optional[str] = None


class PublicationBiasDetector:
    """
    Detects publication bias using MBFC web lookup with local database fallback

    Flow:
    1. Check Supabase database cache first
    2. If not found or stale, search MBFC using Brave Search API
    3. Scrape MBFC page
    4. Verify it's the correct publication
    5. Extract bias/credibility data
    6. Save to Supabase database
    7. Fall back to local database if all else fails
    """

    def __init__(self, config=None, brave_searcher=None, scraper=None):
        """
        Initialize detector with optional dependencies

        Args:
            config: Configuration object with API keys
            brave_searcher: BraveSearcher instance for web search
            scraper: BrowserlessScraper instance for web scraping
        """
        self.config = config
        self.brave_searcher = brave_searcher
        self.scraper = scraper
        self.mbfc_scraper = MBFCScraper(config)

        # Initialize LLM for verification and extraction
        if config and hasattr(config, 'openai_api_key'):
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",  # Fast and cheap for simple extraction
                temperature=0
            ).bind(response_format={"type": "json_object"})
        else:
            self.llm = None

        # Load prompts
        try:
            from prompts.mbfc_prompts import get_verify_prompts, get_extract_prompts
            self.verify_prompts = get_verify_prompts()
            self.extract_prompts = get_extract_prompts()
        except ImportError:
            fact_logger.logger.warning("MBFC prompts not found, using inline prompts")
            self.verify_prompts = None
            self.extract_prompts = None

        # Local publication database (fallback)
        self.publication_database = self._init_local_database()

        # Initialize Supabase service for database storage
        try:
            from utils.supabase_service import get_supabase_service
            self.supabase_service = get_supabase_service(config)
            self.supabase_enabled = self.supabase_service.enabled
            if self.supabase_enabled:
                fact_logger.logger.info("✅ Supabase integration enabled for MBFC storage")
        except ImportError:
            fact_logger.logger.warning("⚠️ Supabase service not found - database caching disabled")
            self.supabase_service = None
            self.supabase_enabled = False
        except Exception as e:
            fact_logger.logger.warning(f"⚠️ Supabase not available: {e}")
            self.supabase_service = None
            self.supabase_enabled = False

        fact_logger.log_component_start(
            "PublicationBiasDetector",
            num_local_publications=len(self.publication_database),
            mbfc_enabled=self.llm is not None,
            supabase_enabled=self.supabase_enabled
        )

    def _init_local_database(self) -> Dict[str, PublicationProfile]:
        """Initialize local publication database as fallback"""
        return {
            # US Publications
            "foxnews.com": PublicationProfile(
                name="Fox News",
                political_leaning="right",
                bias_rating=7.5,
                ownership="Fox Corporation",
                target_audience="Conservative viewers",
                known_biases=["Conservative perspective", "Pro-Republican"],
                credibility_notes="Mixed factual reporting"
            ),
            "cnn.com": PublicationProfile(
                name="CNN",
                political_leaning="center-left",
                bias_rating=5.5,
                ownership="Warner Bros. Discovery",
                target_audience="Liberal-leaning viewers",
                known_biases=["Liberal perspective", "Sensationalism"],
                credibility_notes="Mostly factual with some sensationalism"
            ),
            "nytimes.com": PublicationProfile(
                name="The New York Times",
                political_leaning="center-left",
                bias_rating=5.0,
                ownership="The New York Times Company",
                target_audience="Educated, urban readers",
                known_biases=["Editorial board leans left", "Strong opinion section"],
                credibility_notes="High factual accuracy in news reporting"
            ),
            "washingtonpost.com": PublicationProfile(
                name="The Washington Post",
                political_leaning="center-left",
                bias_rating=5.0,
                ownership="Jeff Bezos",
                target_audience="Political news consumers",
                known_biases=["Liberal editorial stance"],
                credibility_notes="High factual accuracy"
            ),
            "wsj.com": PublicationProfile(
                name="The Wall Street Journal",
                political_leaning="center-right",
                bias_rating=4.5,
                ownership="News Corp (Rupert Murdoch)",
                target_audience="Business professionals",
                known_biases=["Conservative editorial page", "Pro-business"],
                credibility_notes="High factual accuracy in news, conservative opinion"
            ),
            "breitbart.com": PublicationProfile(
                name="Breitbart",
                political_leaning="far-right",
                bias_rating=9.0,
                ownership="Breitbart News Network",
                target_audience="Conservative/nationalist audience",
                known_biases=["Far-right perspective", "Inflammatory content"],
                credibility_notes="Mixed factual reporting, questionable source"
            ),
            # UK Publications
            "telegraph.co.uk": PublicationProfile(
                name="The Telegraph",
                political_leaning="center-right",
                bias_rating=5.5,
                ownership="Telegraph Media Group",
                target_audience="Conservative UK readers",
                known_biases=["Conservative perspective", "Pro-business"],
                credibility_notes="Generally reliable with conservative editorial stance"
            ),
            "theguardian.com": PublicationProfile(
                name="The Guardian",
                political_leaning="left",
                bias_rating=6.0,
                ownership="Scott Trust Limited",
                target_audience="Progressive readers",
                known_biases=["Left-wing editorial stance", "Pro-environment"],
                credibility_notes="High factual accuracy with left-leaning perspective"
            ),
            # Wire Services (most neutral)
            "reuters.com": PublicationProfile(
                name="Reuters",
                political_leaning="center",
                bias_rating=2.0,
                ownership="Thomson Reuters",
                target_audience="General audience",
                known_biases=["Minimal bias", "Fact-focused"],
                credibility_notes="Very high factual accuracy, minimal bias"
            ),
            "apnews.com": PublicationProfile(
                name="Associated Press",
                political_leaning="center",
                bias_rating=2.0,
                ownership="Cooperative owned by member newspapers",
                target_audience="General audience",
                known_biases=["Minimal bias", "Fact-focused"],
                credibility_notes="Very high factual accuracy, minimal bias"
            ),
            "bbc.com": PublicationProfile(
                name="BBC",
                political_leaning="center",
                bias_rating=2.5,
                ownership="British Broadcasting Corporation (publicly funded)",
                target_audience="General UK and international audience",
                known_biases=["Minimal bias", "Occasional pro-establishment tendency"],
                credibility_notes="High factual accuracy with efforts toward balance"
            ),
        }

    @staticmethod
    def clean_url_to_domain(url: str) -> str:
        """
        Clean a URL to get just the root domain

        Examples:
            "https://www.cnn.com/politics/article" -> "cnn.com"
            "cnn.com" -> "cnn.com"
            "www.foxnews.com" -> "foxnews.com"
        """
        if not url:
            return ""

        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Remove www. prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            return domain
        except Exception:
            # If parsing fails, try simple cleanup
            domain = url.lower()
            domain = re.sub(r'^https?://', '', domain)
            domain = re.sub(r'^www\.', '', domain)
            domain = domain.split('/')[0]
            return domain

    async def check_database_first(self, domain: str) -> Optional[MBFCResult]:
        """
        Check Supabase database for existing MBFC data before doing web lookup

        Args:
            domain: The publication domain

        Returns:
            MBFCResult if found in database and not stale, None otherwise
        """
        if not self.supabase_enabled or not self.supabase_service:
            return None

        try:
            record = self.supabase_service.get_credibility_by_domain(domain)

            if not record:
                return None

            # Check if record is recent (within 30 days)
            last_verified = record.get('last_verified_at')
            if last_verified:
                try:
                    # Handle different datetime formats
                    if isinstance(last_verified, str):
                        verified_date = datetime.fromisoformat(last_verified.replace('Z', '+00:00'))
                    else:
                        verified_date = last_verified

                    now = datetime.now(verified_date.tzinfo) if verified_date.tzinfo else datetime.utcnow()
                    if now - verified_date > timedelta(days=30):
                        fact_logger.logger.info(f"📅 Database record for {domain} is stale, will refresh")
                        return None
                except Exception as e:
                    fact_logger.logger.warning(f"Could not parse date: {e}")

            # Convert database record to MBFCResult
            fact_logger.logger.info(f"✅ Found {domain} in database cache")

            # Get publication name from names array or domain
            names = record.get('names', [])
            pub_name = names[0] if names else domain

            return MBFCResult(
                publication_name=pub_name,
                bias_rating=record.get('mbfc_bias_rating'),
                bias_score=record.get('mbfc_bias_score'),
                factual_reporting=record.get('mbfc_factual_reporting'),
                factual_score=record.get('mbfc_factual_score'),
                credibility_rating=record.get('mbfc_credibility_rating'),
                country_freedom_rating=record.get('mbfc_country_freedom_rating'),
                country=record.get('country'),
                media_type=record.get('media_type'),
                traffic_popularity=record.get('traffic_popularity'),
                ownership=record.get('ownership'),
                funding=record.get('funding'),
                failed_fact_checks=record.get('failed_fact_checks', []),
                summary=record.get('mbfc_summary'),
                special_tags=record.get('mbfc_special_tags', []),
                mbfc_url=record.get('mbfc_url')
            )

        except Exception as e:
            fact_logger.logger.warning(f"⚠️ Database lookup failed: {e}")
            return None

    async def save_mbfc_to_database(self, domain: str, mbfc_result: MBFCResult) -> bool:
        """
        Save MBFC lookup result to Supabase database with AI features

        Args:
            domain: The publication domain
            mbfc_result: The extracted MBFC data

        Returns:
            True if saved successfully, False otherwise
        """
        if not self.supabase_enabled or not self.supabase_service:
            return False

        try:
            # Convert MBFCResult to dict
            mbfc_data = mbfc_result.model_dump()

            # Use the complete update with AI features (generates names and tier)
            result = await self.supabase_service.update_with_ai_features(
                domain=domain,
                mbfc_data=mbfc_data
            )

            if result:
                fact_logger.logger.info(f"✅ Saved MBFC data to Supabase: {domain}")
                return True
            return False

        except Exception as e:
            fact_logger.logger.error(f"❌ Failed to save to Supabase: {e}")
            return False

    async def lookup_mbfc(self, domain: str) -> Optional[MBFCResult]:
        """
        Look up publication on MBFC using dedicated MBFC scraper with ad blocking.

        Args:
            domain: Clean domain (e.g., "cnn.com")

        Returns:
            MBFCResult if found and verified, None otherwise
        """
        # Check database first before web lookup
        cached_result = await self.check_database_first(domain)
        if cached_result:
            return cached_result

        if not self.brave_searcher or not self.scraper:
            fact_logger.logger.warning("MBFC lookup not available - missing dependencies")
            return None

        try:
            fact_logger.logger.info(f"Looking for MBFC page: {domain}")

            # Step 1: Search MBFC using site: operator
            search_query = f"site:mediabiasfactcheck.com {domain}"
            results = await self.brave_searcher.search(search_query)

            if not results.results:
                fact_logger.logger.info(f"No MBFC results found for {domain}")
                return None

            # Step 2: Find the most relevant MBFC URL
            mbfc_url = None
            for result in results.results[:5]:
                url = result.get('url', '')
                if '/202' in url:  # Skip blog posts
                    continue
                if 'mediabiasfactcheck.com' in url and '-bias' in url:
                    mbfc_url = url
                    break

            if not mbfc_url:
                for result in results.results[:3]:
                    url = result.get('url', '')
                    if 'mediabiasfactcheck.com' in url:
                        mbfc_url = url
                        break

            if not mbfc_url or 'mediabiasfactcheck.com' not in mbfc_url:
                fact_logger.logger.info(f"No valid MBFC page found for {domain}")
                return None

            fact_logger.logger.info(f"Found MBFC page: {mbfc_url}")

            # Step 3: Initialize browser pool if needed
            await self.scraper._initialize_browser_pool(min_browsers=1)

            if not self.scraper.browser_pool:
                fact_logger.logger.error("No browser available for MBFC scraping")
                return None

            browser = self.scraper.browser_pool[0]
            page = None

            try:
                # Create new page
                page = await browser.new_page()

                # IMPORTANT: Let the MBFC scraper handle everything
                # including ad blocking setup and navigation
                extracted_data = await self.mbfc_scraper.scrape_mbfc_page(page, mbfc_url)

                if not extracted_data:
                    fact_logger.logger.warning(f"Failed to extract data from MBFC page: {mbfc_url}")
                    return None

                # Convert MBFCExtractedData to MBFCResult
                mbfc_result = MBFCResult(
                    publication_name=extracted_data.publication_name,
                    bias_rating=extracted_data.bias_rating,
                    bias_score=extracted_data.bias_score,
                    factual_reporting=extracted_data.factual_reporting,
                    factual_score=extracted_data.factual_score,
                    credibility_rating=extracted_data.credibility_rating,
                    country_freedom_rating=extracted_data.country_freedom_rating,
                    country=extracted_data.country,
                    media_type=extracted_data.media_type,
                    traffic_popularity=extracted_data.traffic_popularity,
                    ownership=extracted_data.ownership,
                    funding=extracted_data.funding,
                    failed_fact_checks=extracted_data.failed_fact_checks,
                    summary=extracted_data.summary,
                    special_tags=extracted_data.special_tags,
                    mbfc_url=mbfc_url
                )

                fact_logger.logger.info(
                    f"MBFC data extracted for {mbfc_result.publication_name}",
                    extra={
                        "bias": mbfc_result.bias_rating,
                        "factual": mbfc_result.factual_reporting,
                        "credibility": mbfc_result.credibility_rating
                    }
                )

                # Save to Supabase database
                if self.supabase_enabled:
                    try:
                        await self.save_mbfc_to_database(domain, mbfc_result)
                    except Exception as e:
                        fact_logger.logger.warning(f"Database save failed (non-critical): {e}")

                return mbfc_result

            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass

        except Exception as e:
            fact_logger.logger.error(f"MBFC lookup failed: {e}", exc_info=True)
            return None

    async def _verify_publication(self, target_domain: str, mbfc_content: str) -> bool:
        """Verify that the MBFC page is about the correct publication"""
        if not self.verify_prompts or not self.llm:
            # Fallback: simple string matching
            return target_domain.replace('.com', '').replace('.co.uk', '') in mbfc_content.lower()

        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.verify_prompts["system"]),
                ("user", self.verify_prompts["user"])
            ])

            chain = prompt | self.llm

            response = await chain.ainvoke({
                "target_domain": target_domain,
                "mbfc_content": mbfc_content[:8000]  # Limit content size
            })

            # Parse response - handle different content types
            content = response.content
            if isinstance(content, str):
                result = json.loads(content)
            else:
                result = json.loads(str(content))

            return result.get("is_match", False)

        except Exception as e:
            fact_logger.logger.error(f"Verification failed: {e}")
            # Fallback to simple matching
            return target_domain.replace('.com', '').replace('.co.uk', '') in mbfc_content.lower()

    async def _extract_bias_data(self, mbfc_content: str) -> Optional[MBFCResult]:
        """Extract structured bias data from MBFC page content"""
        if not self.extract_prompts or not self.llm:
            return None

        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.extract_prompts["system"]),
                ("user", self.extract_prompts["user"])
            ])

            chain = prompt | self.llm

            response = await chain.ainvoke({
                "mbfc_content": mbfc_content[:10000]  # Limit content size
            })

            # Parse response - handle different content types
            content = response.content
            if isinstance(content, str):
                result = json.loads(content)
            else:
                result = json.loads(str(content))

            # Ensure list fields are lists, not None
            if result.get('special_tags') is None:
                result['special_tags'] = []
            elif isinstance(result.get('special_tags'), str):
                result['special_tags'] = [result['special_tags']] if result['special_tags'] else []

            if result.get('failed_fact_checks') is None:
                result['failed_fact_checks'] = []
            elif isinstance(result.get('failed_fact_checks'), str):
                result['failed_fact_checks'] = [result['failed_fact_checks']] if result['failed_fact_checks'] else []

            return MBFCResult(**result)

        except Exception as e:
            fact_logger.logger.error(f"Data extraction failed: {e}")
            return None

    def _convert_mbfc_to_profile(self, mbfc: MBFCResult) -> PublicationProfile:
        """Convert MBFC result to PublicationProfile format"""

        # Map MBFC bias rating to our scale (0-10)
        bias_map = {
            "FAR LEFT": 8.5,
            "LEFT": 6.5,
            "LEFT-CENTER": 4.5,
            "CENTER": 2.0,
            "RIGHT-CENTER": 4.5,
            "RIGHT": 6.5,
            "FAR RIGHT": 8.5,
        }

        # Normalize political leaning
        leaning_map = {
            "FAR LEFT": "far-left",
            "LEFT": "left",
            "LEFT-CENTER": "center-left",
            "CENTER": "center",
            "RIGHT-CENTER": "center-right",
            "RIGHT": "right",
            "FAR RIGHT": "far-right",
        }

        bias_rating_upper = (mbfc.bias_rating or "CENTER").upper()

        # Calculate bias score
        if mbfc.bias_score is not None:
            # MBFC uses negative for left, positive for right
            bias_score = abs(mbfc.bias_score)  # Normalize to 0-10 range
        else:
            bias_score = bias_map.get(bias_rating_upper, 5.0)

        # Build known biases list
        known_biases = []
        if mbfc.bias_rating:
            known_biases.append(f"{mbfc.bias_rating} bias per MBFC")
        if mbfc.special_tags:
            known_biases.extend(mbfc.special_tags)

        # Build credibility notes
        credibility_parts = []
        if mbfc.factual_reporting:
            credibility_parts.append(f"Factual reporting: {mbfc.factual_reporting}")
        if mbfc.credibility_rating:
            credibility_parts.append(f"Credibility: {mbfc.credibility_rating}")
        if mbfc.country_freedom_rating:
            credibility_parts.append(f"Press Freedom: {mbfc.country_freedom_rating}")
        if mbfc.summary:
            credibility_parts.append(mbfc.summary)

        return PublicationProfile(
            name=mbfc.publication_name,
            political_leaning=leaning_map.get(bias_rating_upper, "center"),
            bias_rating=bias_score,
            ownership=mbfc.ownership,
            target_audience=mbfc.media_type,
            known_biases=known_biases,
            credibility_notes=" | ".join(credibility_parts) if credibility_parts else None,
            factual_reporting=mbfc.factual_reporting,
            credibility_rating=mbfc.credibility_rating,
            country_freedom_rating=mbfc.country_freedom_rating,
            mbfc_url=mbfc.mbfc_url,
            failed_fact_checks=mbfc.failed_fact_checks,
            source="mbfc"
        )

    async def detect_publication_async(
        self, 
        publication_url: Optional[str] = None,
        publication_name: Optional[str] = None
    ) -> Optional[PublicationProfile]:
        """
        Detect publication bias - async version with MBFC lookup

        Args:
            publication_url: URL of the publication (preferred)
            publication_name: Name of the publication (fallback)

        Returns:
            PublicationProfile if found, None otherwise
        """
        # Try URL-based lookup first (MBFC)
        if publication_url:
            domain = self.clean_url_to_domain(publication_url)

            if domain:
                # Try MBFC lookup (includes database cache check)
                mbfc_result = await self.lookup_mbfc(domain)

                if mbfc_result:
                    return self._convert_mbfc_to_profile(mbfc_result)

                # Fall back to local database
                if domain in self.publication_database:
                    profile = self.publication_database[domain]
                    fact_logger.logger.info(f"📰 Using local profile for: {domain}")
                    return profile

        # Fall back to name-based lookup (local only)
        if publication_name:
            return self.detect_publication(publication_name)

        return None

    def detect_publication(self, publication_name: Optional[str]) -> Optional[PublicationProfile]:
        """
        Detect publication bias from name (sync version, local database only)

        Args:
            publication_name: Name of the publication (e.g., "The Telegraph")

        Returns:
            PublicationProfile if found, None otherwise
        """
        if not publication_name:
            return None

        # Normalize the name for matching
        normalized_name = publication_name.lower().strip()

        # Try domain-based match first
        for domain, profile in self.publication_database.items():
            if normalized_name in domain or domain.replace('.com', '').replace('.co.uk', '') in normalized_name:
                fact_logger.logger.info(f"📰 Detected publication: {profile.name}")
                return profile

        # Try name-based match
        for domain, profile in self.publication_database.items():
            if normalized_name in profile.name.lower() or profile.name.lower() in normalized_name:
                fact_logger.logger.info(f"📰 Detected publication (name match): {profile.name}")
                return profile

        fact_logger.logger.info(f"📰 Unknown publication: {publication_name}")
        return None

    def get_publication_context(
        self, 
        publication_url: Optional[str] = None,
        publication_name: Optional[str] = None,
        profile: Optional[PublicationProfile] = None
    ) -> str:
        """
        Get formatted context about publication bias for use in prompts

        Args:
            publication_url: URL of the publication
            publication_name: Name of the publication
            profile: Pre-fetched PublicationProfile (if available)

        Returns:
            Formatted string describing publication bias
        """
        if not profile:
            if publication_url:
                domain = self.clean_url_to_domain(publication_url)
                profile = self.publication_database.get(domain)
            elif publication_name:
                profile = self.detect_publication(publication_name)

        if not profile:
            if publication_url:
                return f"PUBLICATION: {publication_url} (unknown publication - no bias profile available)"
            elif publication_name:
                return f"PUBLICATION: {publication_name} (unknown publication - no bias profile available)"
            return "PUBLICATION: Not specified"

        # Build context with all available information
        context_parts = [
            f"PUBLICATION: {profile.name}",
            f"KNOWN POLITICAL LEANING: {profile.political_leaning}",
            f"BIAS RATING: {profile.bias_rating}/10",
        ]

        if profile.factual_reporting:
            context_parts.append(f"FACTUAL REPORTING: {profile.factual_reporting}")

        if profile.credibility_rating:
            context_parts.append(f"CREDIBILITY RATING: {profile.credibility_rating}")

        if profile.country_freedom_rating:
            context_parts.append(f"PRESS FREEDOM RATING: {profile.country_freedom_rating}")

        if profile.assigned_tier:
            context_parts.append(f"ASSIGNED TIER: {profile.assigned_tier}/5")

        if profile.ownership:
            context_parts.append(f"OWNERSHIP: {profile.ownership}")

        if profile.target_audience:
            context_parts.append(f"TARGET AUDIENCE / MEDIA TYPE: {profile.target_audience}")

        if profile.known_biases:
            context_parts.append(f"KNOWN BIASES: {', '.join(profile.known_biases)}")

        if profile.credibility_notes:
            context_parts.append(f"CREDIBILITY NOTES: {profile.credibility_notes}")

        if profile.failed_fact_checks:
            context_parts.append(f"FAILED FACT CHECKS: {len(profile.failed_fact_checks)} on record")

        if profile.mbfc_url:
            context_parts.append(f"SOURCE: Media Bias/Fact Check ({profile.mbfc_url})")
        else:
            context_parts.append(f"SOURCE: {profile.source.capitalize()} database")

        context_parts.append(
            f"\n⚠️ IMPORTANT: This publication has a known {profile.political_leaning} bias. "
            "Consider how this might influence the framing and presentation of information."
        )

        return "\n".join(context_parts)

    def add_publication(self, domain: str, profile: PublicationProfile) -> None:
        """
        Add a new publication to the local database

        Args:
            domain: Domain key (e.g., "example.com")
            profile: PublicationProfile to add
        """
        self.publication_database[domain] = profile
        fact_logger.logger.info(f"➕ Added publication profile: {profile.name}")

    def is_propaganda_source(self, domain: str) -> bool:
        """
        Check if a domain is a known propaganda source

        Args:
            domain: The publication domain

        Returns:
            True if flagged as propaganda, False otherwise
        """
        if self.supabase_enabled and self.supabase_service:
            return self.supabase_service.is_propaganda_source(domain)
        return False

    def get_quick_credibility(self, domain: str) -> Optional[Dict]:
        """
        Get a quick credibility check for a domain

        Args:
            domain: The publication domain

        Returns:
            Dictionary with tier and credibility info, or None
        """
        if self.supabase_enabled and self.supabase_service:
            return self.supabase_service.get_quick_credibility(domain)

        # Fallback to local database
        profile = self.publication_database.get(domain)
        if profile:
            return {
                'domain': domain,
                'tier': 2 if profile.bias_rating < 5 else 3,
                'credibility_rating': profile.credibility_rating,
                'is_propaganda': False,
                'source': 'local'
            }
        return None