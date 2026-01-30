# utils/mbfc_scraper.py
"""
Dedicated MBFC Scraper with Ad Blocking + Optional Login Session

Features:
- Aggressive ad/popup blocking at network level
- Cookie injection for ad-free account access
- Multiple extraction strategies
- AI-powered data extraction with regex fallback
"""

import asyncio
import json
import re
import os
from typing import Optional, List
from pydantic import BaseModel, Field
from playwright.async_api import Browser, Page, BrowserContext

from utils.logger import fact_logger

# Try to import LLM dependencies
try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import ChatPromptTemplate
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    fact_logger.logger.warning("LangChain not available for MBFC AI extraction")


class MBFCExtractedData(BaseModel):
    """Structured data extracted from MBFC page"""
    publication_name: str = Field(description="Name of the publication")
    bias_rating: Optional[str] = Field(default=None, description="Bias rating (e.g., LEFT-CENTER, RIGHT, etc.)")
    bias_score: Optional[float] = Field(default=None, description="Numeric bias score if provided")
    factual_reporting: Optional[str] = Field(default=None, description="Factual reporting level")
    factual_score: Optional[float] = Field(default=None, description="Numeric factual score if provided")
    credibility_rating: Optional[str] = Field(default=None, description="MBFC credibility rating")
    country: Optional[str] = Field(default=None, description="Country of publication")
    country_freedom_rating: Optional[str] = Field(default=None, description="Press freedom rating")
    media_type: Optional[str] = Field(default=None, description="Type of media")
    traffic_popularity: Optional[str] = Field(default=None, description="Traffic/popularity level")
    ownership: Optional[str] = Field(default=None, description="Who owns the publication")
    funding: Optional[str] = Field(default=None, description="How the publication is funded")
    failed_fact_checks: list = Field(default_factory=list, description="List of failed fact checks")
    summary: Optional[str] = Field(default=None, description="Overall summary/rating statement")
    special_tags: list = Field(default_factory=list, description="Special tags")


# Domains to block (ads, tracking, popups)
BLOCKED_DOMAINS = [
    # Google Ads
    'googlesyndication.com',
    'googleadservices.com',
    'doubleclick.net',
    'google-analytics.com',
    'googletagmanager.com',
    'googletagservices.com',
    'pagead2.googlesyndication.com',

    # Ad networks
    'adngin.com',
    'adservice.google.com',
    'adsystem.com',
    'advertising.com',
    'adform.net',
    'adnxs.com',
    'adsrvr.org',
    'amazon-adsystem.com',
    'criteo.com',
    'outbrain.com',
    'taboola.com',
    'pubmatic.com',
    'rubiconproject.com',
    'openx.net',
    'casalemedia.com',
    'contextweb.com',
    'spotxchange.com',
    'tremorhub.com',

    # Tracking
    'facebook.net',
    'facebook.com/tr',
    'connect.facebook.net',
    'chartbeat.com',
    'quantserve.com',
    'scorecardresearch.com',
    'newrelic.com',
    'nr-data.net',
    'segment.io',
    'segment.com',
    'mixpanel.com',
    'hotjar.com',
    'fullstory.com',
    'mouseflow.com',
    'crazyegg.com',

    # Popups / Modals
    'optinmonster.com',
    'sumo.com',
    'mailchimp.com',
    'klaviyo.com',
    'privy.com',
    'justuno.com',

    # MBFC specific ad containers
    'jetpack.wordpress.com',
]

# Resource types to block
BLOCKED_RESOURCE_TYPES = ['image', 'media', 'font', 'stylesheet']


MBFC_EXTRACTION_PROMPT = """You are an expert at extracting structured data from Media Bias/Fact Check (MBFC) pages.

Given the raw text content from an MBFC page, extract all relevant information into a structured format.

IMPORTANT GUIDELINES:
1. Extract EXACT values as they appear (e.g., "LEFT-CENTER", "HIGH", "MOSTLY FREE")
2. For bias_score, look for numbers in parentheses like "(-3.4)" and extract as float
3. For factual_score, look for numbers like "(1.0)" near factual reporting
4. failed_fact_checks should be a list - if "None in the Last 5 years", return empty list []
5. special_tags should include any warning labels like "Questionable Source", "Conspiracy-Pseudoscience", "Satire", etc.
6. If a field is not found, use null

RAW PAGE CONTENT:
{page_content}

Respond with ONLY valid JSON matching this structure:
{{
    "publication_name": "string",
    "bias_rating": "string or null",
    "bias_score": "number or null",
    "factual_reporting": "string or null",
    "factual_score": "number or null",
    "credibility_rating": "string or null",
    "country": "string or null",
    "country_freedom_rating": "string or null",
    "media_type": "string or null",
    "traffic_popularity": "string or null",
    "ownership": "string or null",
    "funding": "string or null",
    "failed_fact_checks": ["list of strings"],
    "summary": "string or null",
    "special_tags": ["list of strings"]
}}"""


class MBFCScraper:
    """
    Dedicated scraper for MBFC pages with aggressive ad blocking.
    """

    def __init__(self, config=None):
        """
        Initialize the MBFC scraper.

        Args:
            config: Configuration object with API keys
        """
        self.config = config
        self.llm = None

        # Get MBFC session cookie from environment if available
        # Set MBFC_SESSION_COOKIE in Railway environment variables
        self.session_cookie = os.getenv('MBFC_SESSION_COOKIE')
        if self.session_cookie:
            fact_logger.logger.info("MBFC Scraper: Ad-free session cookie configured")

        # Initialize LLM for extraction
        if LLM_AVAILABLE and config and hasattr(config, 'openai_api_key'):
            try:
                self.llm = ChatOpenAI(
                    model="gpt-4o-mini",
                    temperature=0
                ).bind(response_format={"type": "json_object"})
                fact_logger.logger.info("MBFC Scraper: AI extraction enabled")
            except Exception as e:
                fact_logger.logger.warning(f"MBFC Scraper: Could not initialize LLM: {e}")

        fact_logger.logger.info("MBFCScraper initialized with ad blocking")

    async def _should_block_request(self, route) -> bool:
        """Check if a request should be blocked."""
        url = route.request.url.lower()
        resource_type = route.request.resource_type

        # Block by resource type (but allow stylesheets for proper rendering)
        if resource_type in ['image', 'media', 'font']:
            return True

        # Block by domain
        for blocked_domain in BLOCKED_DOMAINS:
            if blocked_domain in url:
                return True

        # Block specific URL patterns
        blocked_patterns = [
            '/ads/', '/ad/', '/advert',
            'pagead', 'adsense', 'adserver',
            'tracking', 'analytics',
            'popup', 'modal', 'overlay',
            'newsletter', 'subscribe',
            '.gif', '.png', '.jpg', '.jpeg', '.webp',  # Images by extension
        ]
        for pattern in blocked_patterns:
            if pattern in url:
                return True

        return False

    async def _setup_page_with_blocking(self, page: Page):
        """Configure page with aggressive ad/popup blocking."""

        # Block requests at network level
        async def handle_route(route):
            if await self._should_block_request(route):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", handle_route)

        # Set headers
        await page.set_extra_http_headers({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",  # Do Not Track
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        # Inject script to remove popups and overlays
        await page.add_init_script("""
            // Block popup/modal functions
            window.alert = () => {};
            window.confirm = () => true;
            window.prompt = () => '';

            // Remove elements that might block content
            const removeBlockingElements = () => {
                const selectors = [
                    // Generic popup/modal selectors
                    '[class*="popup"]',
                    '[class*="modal"]',
                    '[class*="overlay"]',
                    '[id*="popup"]',
                    '[id*="modal"]',
                    '[id*="overlay"]',

                    // Cookie consent
                    '[class*="cookie"]',
                    '[id*="cookie"]',
                    '[class*="consent"]',
                    '[id*="consent"]',
                    '[class*="gdpr"]',

                    // Newsletter/subscription popups
                    '[class*="newsletter"]',
                    '[class*="subscribe"]',
                    '[class*="signup"]',

                    // Ad containers
                    '.adsbygoogle',
                    '[class*="adngin"]',
                    '[id*="adngin"]',
                    'ins.adsbygoogle',
                    '[data-ad-slot]',

                    // Fixed/sticky elements that might overlay
                    '[style*="position: fixed"]',
                    '[style*="position:fixed"]',
                ];

                selectors.forEach(selector => {
                    try {
                        document.querySelectorAll(selector).forEach(el => {
                            // Don't remove the main content
                            if (!el.closest('article') && !el.closest('.entry-content')) {
                                el.remove();
                            }
                        });
                    } catch (e) {}
                });

                // Remove any full-screen overlays
                document.querySelectorAll('*').forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' && 
                        (style.zIndex > 1000 || style.width === '100%' || style.height === '100%')) {
                        if (!el.closest('article') && !el.closest('.entry-content')) {
                            el.remove();
                        }
                    }
                });

                // Ensure body is scrollable
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
            };

            // Run immediately and after DOM changes
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', removeBlockingElements);
            } else {
                removeBlockingElements();
            }

            // Also run periodically to catch dynamically added elements
            setInterval(removeBlockingElements, 1000);

            // Observe DOM changes
            const observer = new MutationObserver(removeBlockingElements);
            observer.observe(document.documentElement, { childList: true, subtree: true });
        """)

        # Add session cookie if available
        if self.session_cookie:
            try:
                # Parse cookie string - expects format: "name=value" or full cookie string
                cookies = []
                if '=' in self.session_cookie:
                    # Simple format: "wordpress_logged_in_xxx=value"
                    parts = self.session_cookie.split('=', 1)
                    cookies.append({
                        'name': parts[0].strip(),
                        'value': parts[1].strip(),
                        'domain': '.mediabiasfactcheck.com',
                        'path': '/'
                    })

                if cookies:
                    await page.context.add_cookies(cookies)
                    fact_logger.logger.debug("MBFC Scraper: Session cookie added")
            except Exception as e:
                fact_logger.logger.warning(f"MBFC Scraper: Failed to add session cookie: {e}")

    async def scrape_mbfc_page(
        self, 
        page: Page, 
        url: str
    ) -> Optional[MBFCExtractedData]:
        """
        Scrape an MBFC page with ad blocking.

        Args:
            page: Playwright page object (NOT yet navigated)
            url: The MBFC URL to scrape

        Returns:
            MBFCExtractedData if successful, None otherwise
        """
        try:
            fact_logger.logger.info(f"MBFC Scraper: Setting up page with ad blocking for {url}")

            # Step 1: Setup ad blocking BEFORE navigation
            await self._setup_page_with_blocking(page)

            # Step 2: Navigate to the page
            fact_logger.logger.debug("MBFC Scraper: Navigating to page...")
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)

            # Step 3: Wait for content to load
            await self._wait_for_content(page)

            # Step 4: Clean up any remaining blocking elements
            await self._cleanup_page(page)

            # Step 5: Extract text
            visible_text = await self._get_visible_text(page)

            if not visible_text or len(visible_text) < 200:
                # Debug: get page info
                title = await page.title()
                body_len = await page.evaluate("() => document.body.innerText.length")
                fact_logger.logger.warning(
                    f"MBFC Scraper: Insufficient text extracted ({len(visible_text) if visible_text else 0} chars). "
                    f"Page title: {title}, Body length: {body_len}"
                )
                return None

            fact_logger.logger.info(f"MBFC Scraper: Extracted {len(visible_text)} chars of text")

            # Step 6: Use AI to extract structured data
            extracted_data = await self._extract_with_ai(visible_text)

            if extracted_data:
                fact_logger.logger.info(
                    f"MBFC Scraper: Successfully extracted data for {extracted_data.publication_name}",
                    extra={
                        "publication": extracted_data.publication_name,
                        "bias": extracted_data.bias_rating,
                        "factual": extracted_data.factual_reporting
                    }
                )

            return extracted_data

        except Exception as e:
            fact_logger.logger.error(f"MBFC Scraper: Error scraping {url}: {e}")
            return None

    async def _wait_for_content(self, page: Page):
        """Wait for MBFC content to be fully loaded."""
        # Wait for article element
        try:
            await page.wait_for_selector('article', timeout=10000)
            fact_logger.logger.debug("MBFC Scraper: Article element found")
        except Exception:
            fact_logger.logger.debug("MBFC Scraper: Article not found, continuing...")

        # Wait for entry-content
        try:
            await page.wait_for_selector('.entry-content', timeout=5000)
            fact_logger.logger.debug("MBFC Scraper: Entry-content found")
        except Exception:
            fact_logger.logger.debug("MBFC Scraper: Entry-content not found, continuing...")

        # Wait for specific MBFC content markers
        try:
            await page.wait_for_selector('text=Bias Rating', timeout=5000)
            fact_logger.logger.debug("MBFC Scraper: Bias Rating text found")
        except Exception:
            pass

        # Let JavaScript settle
        await asyncio.sleep(2)

        # Wait for network idle
        try:
            await page.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            pass

    async def _cleanup_page(self, page: Page):
        """Remove any remaining blocking elements after page load."""
        try:
            await page.evaluate("""
                () => {
                    // Remove ad containers
                    const adSelectors = [
                        '.adsbygoogle',
                        '[class*="adngin"]',
                        '[id*="adngin"]',
                        'ins.adsbygoogle',
                        '[data-ad-slot]',
                        'script[src*="adsbygoogle"]',
                        'script[src*="pagead"]',
                    ];

                    adSelectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => el.remove());
                    });

                    // Remove fixed position overlays
                    document.querySelectorAll('*').forEach(el => {
                        const style = window.getComputedStyle(el);
                        if (style.position === 'fixed' && style.zIndex > 100) {
                            const rect = el.getBoundingClientRect();
                            // If it covers a significant portion of the screen
                            if (rect.width > window.innerWidth * 0.5 || 
                                rect.height > window.innerHeight * 0.5) {
                                el.remove();
                            }
                        }
                    });

                    // Ensure scrolling works
                    document.body.style.overflow = 'auto';
                    document.documentElement.style.overflow = 'auto';
                }
            """)
            fact_logger.logger.debug("MBFC Scraper: Page cleanup complete")
        except Exception as e:
            fact_logger.logger.debug(f"MBFC Scraper: Page cleanup error (non-critical): {e}")

    async def _get_visible_text(self, page: Page) -> str:
        """Extract visible text from the page."""
        try:
            text = await page.evaluate("""
                () => {
                    // Try specific MBFC selectors first
                    const selectors = [
                        'article',
                        '.entry-content.clearfix',
                        '.entry-content',
                        '#main-content',
                        '[role="main"]'
                    ];

                    for (const selector of selectors) {
                        const el = document.querySelector(selector);
                        if (el) {
                            const text = el.innerText;
                            if (text && text.length > 500) {
                                return text;
                            }
                        }
                    }

                    // Fallback to body
                    return document.body.innerText;
                }
            """)

            return self._clean_text(text) if text else ""

        except Exception as e:
            fact_logger.logger.error(f"MBFC Scraper: Text extraction error: {e}")
            return ""

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text."""
        if not text:
            return ""

        # Remove excessive whitespace
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        text = re.sub(r'[ \t]+', ' ', text)

        # Remove common noise
        noise_patterns = [
            r'Advertisement\s*\n',
            r'Skip to content\s*\n',
            r'Search for:.*?\n',
        ]
        for pattern in noise_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        return text.strip()

    async def _extract_with_ai(self, page_content: str) -> Optional[MBFCExtractedData]:
        """Use AI to extract structured data."""
        if not self.llm:
            fact_logger.logger.info("MBFC Scraper: Using regex extraction (LLM not available)")
            return self._extract_with_regex(page_content)

        try:
            content_for_llm = page_content[:8000] if len(page_content) > 8000 else page_content

            prompt = ChatPromptTemplate.from_messages([
                ("user", MBFC_EXTRACTION_PROMPT)
            ])

            chain = prompt | self.llm
            response = await chain.ainvoke({"page_content": content_for_llm})

            content = response.content
            if isinstance(content, str):
                data = json.loads(content)
            else:
                data = json.loads(str(content))

            if data.get('failed_fact_checks') is None:
                data['failed_fact_checks'] = []
            if data.get('special_tags') is None:
                data['special_tags'] = []

            return MBFCExtractedData(**data)

        except Exception as e:
            fact_logger.logger.error(f"MBFC Scraper: AI extraction failed: {e}")
            return self._extract_with_regex(page_content)

    def _extract_with_regex(self, page_content: str) -> Optional[MBFCExtractedData]:
        """Fallback regex-based extraction."""
        try:
            data = {}

            # Publication name
            title_match = re.search(r'^([^–\-\n]+?)(?:\s*[–\-]\s*Bias)', page_content, re.MULTILINE)
            if title_match:
                data['publication_name'] = title_match.group(1).strip()
            else:
                name_match = re.search(r'Overall,?\s+we\s+rate\s+([^,]+)', page_content, re.IGNORECASE)
                data['publication_name'] = name_match.group(1).strip() if name_match else "Unknown"

            # Bias rating
            bias_match = re.search(r'Bias Rating:\s*([A-Z\-]+(?:\s+[A-Z\-]+)?)\s*\(?([\-\d.]+)?\)?', page_content, re.IGNORECASE)
            if bias_match:
                data['bias_rating'] = bias_match.group(1).strip()
                if bias_match.group(2):
                    try:
                        data['bias_score'] = float(bias_match.group(2))
                    except ValueError:
                        pass

            # Factual reporting
            factual_match = re.search(r'Factual Reporting:\s*([A-Z\s]+)\s*\(?([\d.]+)?\)?', page_content, re.IGNORECASE)
            if factual_match:
                data['factual_reporting'] = factual_match.group(1).strip()
                if factual_match.group(2):
                    try:
                        data['factual_score'] = float(factual_match.group(2))
                    except ValueError:
                        pass

            # Credibility rating
            cred_match = re.search(r'MBFC Credibility Rating:\s*([A-Z\s]+)', page_content, re.IGNORECASE)
            if cred_match:
                data['credibility_rating'] = cred_match.group(1).strip()

            # Country
            country_match = re.search(r'Country:\s*([A-Za-z\s]+?)(?:\n|MBFC)', page_content)
            if country_match:
                data['country'] = country_match.group(1).strip()

            # Country freedom rating
            freedom_match = re.search(r"Country Freedom Rating:\s*([A-Z\s]+)", page_content, re.IGNORECASE)
            if freedom_match:
                data['country_freedom_rating'] = freedom_match.group(1).strip()

            # Media type
            media_match = re.search(r'Media Type:\s*([A-Za-z\s]+?)(?:\n|Traffic)', page_content)
            if media_match:
                data['media_type'] = media_match.group(1).strip()

            # Traffic
            traffic_match = re.search(r'Traffic/Popularity:\s*([A-Za-z\s]+?)(?:\n|MBFC)', page_content)
            if traffic_match:
                data['traffic_popularity'] = traffic_match.group(1).strip()

            # Failed fact checks
            data['failed_fact_checks'] = []

            # Special tags
            special_tags = []
            for pattern in ['Questionable Source', 'Conspiracy-Pseudoscience', 'Satire', 'Pro-Science', 'Propaganda']:
                if re.search(pattern, page_content, re.IGNORECASE):
                    special_tags.append(pattern)
            data['special_tags'] = special_tags

            if data.get('publication_name') and (data.get('bias_rating') or data.get('factual_reporting')):
                return MBFCExtractedData(**data)

            return None

        except Exception as e:
            fact_logger.logger.error(f"MBFC Scraper: Regex extraction failed: {e}")
            return None