# utils/mbfc_scraper.py
"""
Dedicated MBFC Scraper with Human-like Text Selection + AI Extraction

This module provides a specialized scraper for Media Bias/Fact Check pages
that uses a "select all + copy" approach to reliably capture page content,
then uses AI to extract structured data.

This approach is more robust than CSS selector-based extraction for MBFC's
complex WordPress structure with nested elements and ad containers.
"""

import asyncio
import json
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from playwright.async_api import Browser, Page

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
    factual_reporting: Optional[str] = Field(default=None, description="Factual reporting level (HIGH, MOSTLY FACTUAL, MIXED, LOW, VERY LOW)")
    factual_score: Optional[float] = Field(default=None, description="Numeric factual score if provided")
    credibility_rating: Optional[str] = Field(default=None, description="MBFC credibility rating")
    country: Optional[str] = Field(default=None, description="Country of publication")
    country_freedom_rating: Optional[str] = Field(default=None, description="Press freedom rating for the country")
    media_type: Optional[str] = Field(default=None, description="Type of media (Newspaper, Website, TV, etc.)")
    traffic_popularity: Optional[str] = Field(default=None, description="Traffic/popularity level")
    ownership: Optional[str] = Field(default=None, description="Who owns the publication")
    funding: Optional[str] = Field(default=None, description="How the publication is funded")
    failed_fact_checks: list = Field(default_factory=list, description="List of failed fact checks")
    summary: Optional[str] = Field(default=None, description="Overall summary/rating statement")
    special_tags: list = Field(default_factory=list, description="Special tags like 'Questionable Source', 'Conspiracy', etc.")


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
    Dedicated scraper for MBFC pages using human-like interaction.
    
    Uses Ctrl+A to select all visible text, then AI to extract structured data.
    This bypasses issues with complex CSS selectors and nested ad containers.
    """
    
    def __init__(self, config=None):
        """
        Initialize the MBFC scraper.
        
        Args:
            config: Configuration object with API keys
        """
        self.config = config
        self.llm = None
        
        # Initialize LLM for extraction
        if LLM_AVAILABLE and config and hasattr(config, 'openai_api_key'):
            try:
                self.llm = ChatOpenAI(
                    model="gpt-4o-mini",  # Fast and cheap for extraction
                    temperature=0
                ).bind(response_format={"type": "json_object"})
                fact_logger.logger.info("MBFC Scraper: AI extraction enabled")
            except Exception as e:
                fact_logger.logger.warning(f"MBFC Scraper: Could not initialize LLM: {e}")
        
        fact_logger.logger.info("MBFCScraper initialized")
    
    async def scrape_mbfc_page(
        self, 
        page: Page, 
        url: str
    ) -> Optional[MBFCExtractedData]:
        """
        Scrape an MBFC page using human-like text selection.
        
        Args:
            page: Playwright page object (already navigated to MBFC URL)
            url: The MBFC URL being scraped
            
        Returns:
            MBFCExtractedData if successful, None otherwise
        """
        try:
            fact_logger.logger.info(f"MBFC Scraper: Extracting content from {url}")
            
            # Step 1: Get visible text using human-like selection
            visible_text = await self._get_visible_text_human_like(page)
            
            if not visible_text or len(visible_text) < 200:
                fact_logger.logger.warning(f"MBFC Scraper: Insufficient text extracted ({len(visible_text) if visible_text else 0} chars)")
                return None
            
            fact_logger.logger.info(f"MBFC Scraper: Extracted {len(visible_text)} chars of visible text")
            
            # Step 2: Use AI to extract structured data
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
    
    async def _get_visible_text_human_like(self, page: Page) -> str:
        """
        Extract visible text using human-like Ctrl+A selection.
        
        This method:
        1. Clicks on the main content area to focus it
        2. Uses Ctrl+A to select all text
        3. Retrieves the selection
        
        Args:
            page: Playwright page object
            
        Returns:
            Visible text content
        """
        try:
            # Method 1: Use document.body.innerText (most reliable for visible text)
            # This automatically excludes hidden elements, scripts, styles
            visible_text = await page.evaluate("""
                () => {
                    // Get all text content, excluding hidden elements
                    function getVisibleText() {
                        // Create a TreeWalker to iterate through text nodes
                        const walker = document.createTreeWalker(
                            document.body,
                            NodeFilter.SHOW_TEXT,
                            {
                                acceptNode: function(node) {
                                    // Skip if parent is script, style, or hidden
                                    const parent = node.parentElement;
                                    if (!parent) return NodeFilter.FILTER_REJECT;
                                    
                                    const tagName = parent.tagName.toLowerCase();
                                    if (['script', 'style', 'noscript', 'iframe'].includes(tagName)) {
                                        return NodeFilter.FILTER_REJECT;
                                    }
                                    
                                    // Check if element is visible
                                    const style = window.getComputedStyle(parent);
                                    if (style.display === 'none' || style.visibility === 'hidden') {
                                        return NodeFilter.FILTER_REJECT;
                                    }
                                    
                                    // Skip empty text nodes
                                    if (!node.textContent.trim()) {
                                        return NodeFilter.FILTER_REJECT;
                                    }
                                    
                                    return NodeFilter.FILTER_ACCEPT;
                                }
                            }
                        );
                        
                        const textParts = [];
                        let node;
                        while (node = walker.nextNode()) {
                            textParts.push(node.textContent.trim());
                        }
                        
                        return textParts.join(' ');
                    }
                    
                    // Alternative: just use innerText which handles visibility
                    // This is simpler and usually works well
                    const mainContent = document.querySelector('article') || 
                                       document.querySelector('[role="main"]') ||
                                       document.querySelector('main') ||
                                       document.body;
                    
                    return mainContent.innerText;
                }
            """)
            
            # Clean up the text
            if visible_text:
                # Remove excessive whitespace
                import re
                visible_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', visible_text)
                visible_text = re.sub(r'[ \t]+', ' ', visible_text)
                visible_text = visible_text.strip()
            
            return visible_text
            
        except Exception as e:
            fact_logger.logger.error(f"MBFC Scraper: Error getting visible text: {e}")
            
            # Fallback: try simple body.innerText
            try:
                return await page.evaluate("() => document.body.innerText")
            except Exception:
                return ""
    
    async def _extract_with_ai(self, page_content: str) -> Optional[MBFCExtractedData]:
        """
        Use AI to extract structured data from raw page text.
        
        Args:
            page_content: Raw visible text from the page
            
        Returns:
            MBFCExtractedData if successful, None otherwise
        """
        if not self.llm:
            fact_logger.logger.warning("MBFC Scraper: LLM not available, falling back to regex extraction")
            return self._extract_with_regex(page_content)
        
        try:
            # Truncate content if too long (keep first 8000 chars which should have all the data)
            content_for_llm = page_content[:8000] if len(page_content) > 8000 else page_content
            
            prompt = ChatPromptTemplate.from_messages([
                ("user", MBFC_EXTRACTION_PROMPT)
            ])
            
            chain = prompt | self.llm
            
            response = await chain.ainvoke({"page_content": content_for_llm})
            
            # Parse the JSON response
            content = response.content
            if isinstance(content, str):
                data = json.loads(content)
            else:
                data = json.loads(str(content))
            
            # Ensure list fields are lists
            if data.get('failed_fact_checks') is None:
                data['failed_fact_checks'] = []
            if data.get('special_tags') is None:
                data['special_tags'] = []
            
            return MBFCExtractedData(**data)
            
        except json.JSONDecodeError as e:
            fact_logger.logger.error(f"MBFC Scraper: Failed to parse AI response as JSON: {e}")
            return self._extract_with_regex(page_content)
        except Exception as e:
            fact_logger.logger.error(f"MBFC Scraper: AI extraction failed: {e}")
            return self._extract_with_regex(page_content)
    
    def _extract_with_regex(self, page_content: str) -> Optional[MBFCExtractedData]:
        """
        Fallback regex-based extraction when AI is not available.
        
        Args:
            page_content: Raw visible text from the page
            
        Returns:
            MBFCExtractedData if successful, None otherwise
        """
        import re
        
        try:
            data = {}
            
            # Extract publication name from title pattern
            title_match = re.search(r'^([^–\-]+?)(?:\s*[–\-]\s*Bias)', page_content, re.MULTILINE)
            if title_match:
                data['publication_name'] = title_match.group(1).strip()
            else:
                # Try to find it another way
                name_match = re.search(r'Overall,?\s+we\s+rate\s+([^,]+)', page_content, re.IGNORECASE)
                if name_match:
                    data['publication_name'] = name_match.group(1).strip()
                else:
                    data['publication_name'] = "Unknown"
            
            # Extract bias rating
            bias_match = re.search(r'Bias Rating:\s*([A-Z\-]+(?:\s+[A-Z\-]+)?)\s*\(?([\-\d.]+)?\)?', page_content, re.IGNORECASE)
            if bias_match:
                data['bias_rating'] = bias_match.group(1).strip()
                if bias_match.group(2):
                    try:
                        data['bias_score'] = float(bias_match.group(2))
                    except ValueError:
                        pass
            
            # Extract factual reporting
            factual_match = re.search(r'Factual Reporting:\s*([A-Z\s]+)\s*\(?([\d.]+)?\)?', page_content, re.IGNORECASE)
            if factual_match:
                data['factual_reporting'] = factual_match.group(1).strip()
                if factual_match.group(2):
                    try:
                        data['factual_score'] = float(factual_match.group(2))
                    except ValueError:
                        pass
            
            # Extract credibility rating
            cred_match = re.search(r'MBFC Credibility Rating:\s*([A-Z\s]+)', page_content, re.IGNORECASE)
            if cred_match:
                data['credibility_rating'] = cred_match.group(1).strip()
            
            # Extract country
            country_match = re.search(r'Country:\s*([A-Za-z\s]+?)(?:\n|MBFC)', page_content)
            if country_match:
                data['country'] = country_match.group(1).strip()
            
            # Extract country freedom rating
            freedom_match = re.search(r"Country Freedom Rating:\s*([A-Z\s]+)", page_content, re.IGNORECASE)
            if freedom_match:
                data['country_freedom_rating'] = freedom_match.group(1).strip()
            
            # Extract media type
            media_match = re.search(r'Media Type:\s*([A-Za-z\s]+?)(?:\n|Traffic)', page_content)
            if media_match:
                data['media_type'] = media_match.group(1).strip()
            
            # Extract traffic/popularity
            traffic_match = re.search(r'Traffic/Popularity:\s*([A-Za-z\s]+?)(?:\n|MBFC)', page_content)
            if traffic_match:
                data['traffic_popularity'] = traffic_match.group(1).strip()
            
            # Check for failed fact checks
            if re.search(r'None in the Last 5 years', page_content, re.IGNORECASE):
                data['failed_fact_checks'] = []
            else:
                # Try to extract failed fact check entries
                data['failed_fact_checks'] = []
            
            # Check for special tags
            special_tags = []
            tag_patterns = [
                r'Questionable Source',
                r'Conspiracy-Pseudoscience',
                r'Satire',
                r'Pro-Science',
                r'Propaganda'
            ]
            for pattern in tag_patterns:
                if re.search(pattern, page_content, re.IGNORECASE):
                    special_tags.append(pattern)
            data['special_tags'] = special_tags
            
            # Only return if we got at least the publication name and one rating
            if data.get('publication_name') and (data.get('bias_rating') or data.get('factual_reporting')):
                return MBFCExtractedData(**data)
            
            return None
            
        except Exception as e:
            fact_logger.logger.error(f"MBFC Scraper: Regex extraction failed: {e}")
            return None


async def scrape_mbfc_with_browser(
    browser: Browser,
    url: str,
    config=None,
    timeout: int = 15000
) -> Optional[MBFCExtractedData]:
    """
    Convenience function to scrape an MBFC page with a browser instance.
    
    Args:
        browser: Playwright Browser instance
        url: MBFC URL to scrape
        config: Configuration object with API keys
        timeout: Page load timeout in milliseconds
        
    Returns:
        MBFCExtractedData if successful, None otherwise
    """
    scraper = MBFCScraper(config)
    page = None
    
    try:
        page = await browser.new_page()
        
        # Set a reasonable user agent
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        })
        
        # Navigate to the page
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        
        # Wait a moment for any dynamic content
        await asyncio.sleep(1)
        
        # Extract data
        return await scraper.scrape_mbfc_page(page, url)
        
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


# For testing
if __name__ == "__main__":
    import asyncio
    from playwright.async_api import async_playwright
    
    async def test():
        print("Testing MBFC Scraper...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            test_url = "https://mediabiasfactcheck.com/le-monde-bias/"
            
            # Create a simple config mock
            class MockConfig:
                openai_api_key = None  # Will use regex fallback
            
            result = await scrape_mbfc_with_browser(
                browser, 
                test_url, 
                config=MockConfig()
            )
            
            if result:
                print(f"\nExtracted Data:")
                print(f"  Publication: {result.publication_name}")
                print(f"  Bias: {result.bias_rating} ({result.bias_score})")
                print(f"  Factual: {result.factual_reporting} ({result.factual_score})")
                print(f"  Credibility: {result.credibility_rating}")
                print(f"  Country: {result.country}")
                print(f"  Freedom: {result.country_freedom_rating}")
            else:
                print("Failed to extract data")
            
            await browser.close()
    
    asyncio.run(test())
