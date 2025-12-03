# agents/publication_bias_detector.py
"""
Publication Bias Detector with MBFC Integration
Identifies political leanings and biases of news sources using:
1. Local database (fast fallback)
2. Media Bias/Fact Check (MBFC) web lookup (primary source)
"""

from typing import Dict, Optional, List
from pydantic import BaseModel, Field
from urllib.parse import urlparse
import asyncio
import re
import json

from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

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
    # New MBFC-specific fields
    factual_reporting: Optional[str] = None
    credibility_rating: Optional[str] = None
    mbfc_url: Optional[str] = None
    failed_fact_checks: List[str] = []
    source: str = "local"  # "local" or "mbfc"


class MBFCResult(BaseModel):
    """Structured result from MBFC lookup"""
    publication_name: str
    bias_rating: Optional[str] = None
    bias_score: Optional[float] = None
    factual_reporting: Optional[str] = None
    factual_score: Optional[float] = None
    credibility_rating: Optional[str] = None
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
    1. Clean input URL to get root domain
    2. Search MBFC using Brave Search API
    3. Scrape MBFC page
    4. Verify it's the correct publication
    5. Extract bias/credibility data
    6. Fall back to local database if MBFC lookup fails
    """
    
    def __init__(self, config=None, brave_searcher=None, scraper=None):
        """
        Initialize detector with optional dependencies
        
        Args:
            config: Configuration object with API keys
            brave_searcher: BraveSearcher instance for web search
            scraper: FactCheckScraper instance for web scraping
        """
        self.config = config
        self.brave_searcher = brave_searcher
        self.scraper = scraper
        
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
        
        fact_logger.log_component_start(
            "PublicationBiasDetector",
            num_local_publications=len(self.publication_database),
            mbfc_enabled=self.llm is not None
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
                target_audience="Mainstream liberal-leaning viewers",
                known_biases=["Liberal perspective", "Pro-Democratic at times"],
                credibility_notes="Generally factual with some left-leaning editorial choices"
            ),
            "nytimes.com": PublicationProfile(
                name="The New York Times",
                political_leaning="center-left",
                bias_rating=4.5,
                ownership="The New York Times Company",
                target_audience="Educated, liberal-leaning readers",
                known_biases=["Liberal editorial stance", "Urban perspective"],
                credibility_notes="High factual accuracy with center-left editorial perspective"
            ),
            "wsj.com": PublicationProfile(
                name="Wall Street Journal",
                political_leaning="center-right",
                bias_rating=4.0,
                ownership="News Corp",
                target_audience="Business professionals, conservatives",
                known_biases=["Conservative editorial page", "Pro-business"],
                credibility_notes="High factual news reporting with conservative editorial section"
            ),
            "breitbart.com": PublicationProfile(
                name="Breitbart News",
                political_leaning="right",
                bias_rating=9.0,
                ownership="Breitbart News Network",
                target_audience="Far-right conservatives",
                known_biases=["Far-right perspective", "Nationalist", "Anti-immigration"],
                credibility_notes="Mixed factual reporting with extreme right-wing bias"
            ),
            # UK Publications
            "telegraph.co.uk": PublicationProfile(
                name="The Telegraph",
                political_leaning="center-right",
                bias_rating=5.5,
                ownership="The Telegraph Media Group",
                target_audience="Conservative readers in UK",
                known_biases=["Conservative perspective", "Pro-Brexit"],
                credibility_notes="Generally reliable with conservative editorial stance"
            ),
            "theguardian.com": PublicationProfile(
                name="The Guardian",
                political_leaning="center-left",
                bias_rating=5.0,
                ownership="Guardian Media Group",
                target_audience="Progressive readers in UK",
                known_biases=["Liberal-left perspective", "Environmental focus"],
                credibility_notes="High factual accuracy with left-leaning editorial perspective"
            ),
            "dailymail.co.uk": PublicationProfile(
                name="Daily Mail",
                political_leaning="right",
                bias_rating=7.0,
                ownership="Daily Mail and General Trust",
                target_audience="Middle-class conservatives in UK",
                known_biases=["Right-wing populism", "Sensationalist"],
                credibility_notes="Factually mixed with strong right-wing bias"
            ),
            # Neutral/Centrist
            "reuters.com": PublicationProfile(
                name="Reuters",
                political_leaning="center",
                bias_rating=2.0,
                ownership="Thomson Reuters",
                target_audience="General audience, journalists",
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
    
    async def lookup_mbfc(self, domain: str) -> Optional[MBFCResult]:
        """
        Look up publication on MBFC using web search and scraping
        
        Args:
            domain: Clean domain (e.g., "cnn.com")
            
        Returns:
            MBFCResult if found and verified, None otherwise
        """
        if not self.brave_searcher or not self.scraper or not self.llm:
            fact_logger.logger.warning("MBFC lookup not available - missing dependencies")
            return None
        
        try:
            fact_logger.logger.info(f"🔍 Searching MBFC for: {domain}")
            
            # Step 1: Search MBFC using site: operator
            # Brave Search supports site: operator like Google
            search_query = f"site:mediabiasfactcheck.com {domain}"
            
            results = await self.brave_searcher.search(search_query)
            
            if not results.results:
                fact_logger.logger.info(f"📭 No MBFC results found for {domain}")
                return None
            
            # Step 2: Find the most relevant MBFC URL
            # Look for URLs that are direct publication pages (not blog posts or comparisons)
            mbfc_url = None
            for result in results.results[:5]:  # Check top 5 results
                url = result.get('url', '')
                # Skip blog posts, comparison pages, etc.
                if '/202' in url:  # Blog post URLs contain year
                    continue
                if 'mediabiasfactcheck.com' in url:
                    mbfc_url = url
                    break
            
            if not mbfc_url:
                # Fall back to first result if no better match
                mbfc_url = results.results[0].get('url', '')
            
            if not mbfc_url or 'mediabiasfactcheck.com' not in mbfc_url:
                fact_logger.logger.info(f"📭 No valid MBFC page found for {domain}")
                return None
            
            fact_logger.logger.info(f"📰 Found MBFC page: {mbfc_url}")
            
            # Step 3: Scrape the MBFC page
            await self.scraper.ensure_session()
            scraped_content = await self.scraper.scrape_urls([mbfc_url])
            
            mbfc_content = scraped_content.get(mbfc_url, '')
            if not mbfc_content or len(mbfc_content) < 200:
                fact_logger.logger.warning(f"⚠️ Failed to scrape MBFC page: {mbfc_url}")
                return None
            
            # Step 4: Verify this is the correct publication
            is_verified = await self._verify_publication(domain, mbfc_content)
            
            if not is_verified:
                fact_logger.logger.info(f"❌ MBFC page does not match {domain}")
                return None
            
            # Step 5: Extract bias data
            mbfc_result = await self._extract_bias_data(mbfc_content)
            
            if mbfc_result:
                mbfc_result.mbfc_url = mbfc_url
                fact_logger.logger.info(
                    f"✅ MBFC data extracted for {mbfc_result.publication_name}",
                    extra={
                        "bias": mbfc_result.bias_rating,
                        "factual": mbfc_result.factual_reporting,
                        "credibility": mbfc_result.credibility_rating
                    }
                )
            
            return mbfc_result
            
        except Exception as e:
            fact_logger.logger.error(f"❌ MBFC lookup failed: {e}", exc_info=True)
            return None
    
    async def _verify_publication(self, target_domain: str, mbfc_content: str) -> bool:
        """Verify that the MBFC page is about the correct publication"""
        if not self.verify_prompts:
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
            
            # Parse response
            result = json.loads(response.content)
            return result.get("is_match", False)
            
        except Exception as e:
            fact_logger.logger.error(f"Verification failed: {e}")
            # Fallback to simple matching
            return target_domain.replace('.com', '').replace('.co.uk', '') in mbfc_content.lower()
    
    async def _extract_bias_data(self, mbfc_content: str) -> Optional[MBFCResult]:
        """Extract structured bias data from MBFC page content"""
        if not self.extract_prompts:
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
            
            # Parse response
            result = json.loads(response.content)
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
                # Try MBFC lookup
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
            context_parts.append(f"SOURCE: Local database")
        
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
