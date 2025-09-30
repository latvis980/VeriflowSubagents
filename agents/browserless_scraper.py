# agents/browserless_scraper.py
"""
Fact-Checking Web Scraper with Railway Browserless Integration
Structure-preserving content extraction for source verification

KEY FEATURES:
- Railway Browserless optimization for cloud deployment
- Structure-preserving extraction (headings and paragraphs)
- Ad/tracker blocking for faster scraping
- Domain-specific timeout handling
- Comprehensive error handling and logging
"""

import asyncio
import time
import re
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse
from playwright.async_api import async_playwright, Browser, Page

from utils.logger import fact_logger

class FactCheckScraper:
    """
    Web scraper optimized for fact-checking source extraction
    Uses Railway Browserless for cloud deployment
    """

    def __init__(self, config):
        self.config = config
        self.max_concurrent = 2  # Limit concurrent scrapes

        # Railway Browserless endpoint detection
        self.browserless_endpoint = os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE')

        if self.browserless_endpoint:
            fact_logger.logger.info(f"🔗 Browserless endpoint: {self.browserless_endpoint[:50]}...")
        else:
            fact_logger.logger.warning("❌ No BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE found")

        # Timeout configuration
        self.default_timeout = 30000  # 30 seconds
        self.slow_timeout = 60000     # 60 seconds for slow sites
        self.browser_launch_timeout = 30000

        # Domain-specific timeouts for known slow sites
        self.domain_timeouts = {
            'nytimes.com': 45000,
            'washingtonpost.com': 45000,
            'wsj.com': 45000,
            'forbes.com': 40000,
        }

        # Human-like timing
        self.load_wait_time = 2.0      # Wait after page load
        self.interaction_delay = 0.5   # Delay between actions

        # Stats tracking
        self.stats = {
            "total_scraped": 0,
            "successful_scrapes": 0,
            "failed_scrapes": 0,
            "avg_scrape_time": 0.0,
            "total_processing_time": 0.0,
            "structure_preserving_success": 0,
        }

        fact_logger.log_component_start(
            "FactCheckScraper",
            browserless=bool(self.browserless_endpoint)
        )

    async def scrape_urls_for_facts(self, urls: List[str]) -> Dict[str, str]:
        """
        Scrape multiple URLs and return clean content
        Returns: {url: scraped_content}
        """
        if not urls:
            fact_logger.logger.warning("No URLs provided for scraping")
            return {}

        fact_logger.logger.info(
            f"Starting scrape of {len(urls)} URLs",
            extra={"url_count": len(urls)}
        )

        # Process URLs with concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent)
        tasks = [
            self._scrape_with_semaphore(semaphore, url)
            for url in urls
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert to dict and handle exceptions
        results = {}
        for url, result in zip(urls, results_list):
            if isinstance(result, Exception):
                fact_logger.logger.error(
                    f"Scraping failed for {url}: {result}",
                    extra={"url": url, "error": str(result)}
                )
                results[url] = ""
            else:
                results[url] = result

        successful = len([v for v in results.values() if v])
        fact_logger.logger.info(
            f"Scraping complete: {successful}/{len(urls)} successful",
            extra={"successful": successful, "total": len(urls)}
        )

        return results

    async def _scrape_with_semaphore(self, semaphore: asyncio.Semaphore, url: str) -> str:
        """Scrape single URL with concurrency control"""
        async with semaphore:
            return await self._scrape_single_url(url)

    async def _scrape_single_url(self, url: str) -> str:
        """Scrape a single URL with structure preservation"""
        start_time = time.time()
        self.stats["total_scraped"] += 1

        try:
            content = await self._extract_content_with_structure(url)

            if content and len(content.strip()) > 100:
                # Success
                processing_time = time.time() - start_time
                self.stats["successful_scrapes"] += 1
                self.stats["total_processing_time"] += processing_time
                self.stats["avg_scrape_time"] = (
                    self.stats["total_processing_time"] / self.stats["total_scraped"]
                )

                # Count structural elements
                heading_count = len([
                    line for line in content.split('\n') 
                    if line.strip().startswith('#')
                ])

                if heading_count > 0:
                    self.stats["structure_preserving_success"] += 1

                fact_logger.logger.info(
                    f"Successfully scraped: {url}",
                    extra={
                        "url": url,
                        "duration": processing_time,
                        "content_length": len(content),
                        "headings": heading_count
                    }
                )

                return content
            else:
                # Content too short
                processing_time = time.time() - start_time
                self.stats["failed_scrapes"] += 1

                fact_logger.logger.warning(
                    f"Insufficient content from {url}",
                    extra={"url": url, "duration": processing_time}
                )

                return ""

        except Exception as e:
            processing_time = time.time() - start_time
            self.stats["failed_scrapes"] += 1

            fact_logger.logger.error(
                f"Scraping error for {url}: {e}",
                extra={"url": url, "duration": processing_time, "error": str(e)}
            )

            return ""

    async def _extract_content_with_structure(self, url: str) -> str:
        """
        Extract content while preserving structure (headings, paragraphs)
        Uses Railway Browserless if available, local Playwright otherwise
        """
        playwright = None
        browser = None
        page = None

        try:
            # Get domain-specific timeout
            domain = urlparse(url).netloc.lower()
            timeout = self.domain_timeouts.get(domain, self.default_timeout)

            fact_logger.logger.debug(
                f"Extracting content from {url}",
                extra={"url": url, "timeout_ms": timeout, "domain": domain}
            )

            # Initialize Playwright
            playwright = await async_playwright().start()

            # 🔧 FIXED: Correct Railway Browserless connection
            if self.browserless_endpoint:
                # ✅ PROPER CONNECTION METHOD for Railway Browserless
                try:
                    fact_logger.logger.info(f"Connecting to Railway Browserless: {self.browserless_endpoint}")

                    # Use chromium.connect() with the Railway endpoint
                    browser = await playwright.chromium.connect(
                        self.browserless_endpoint,
                        timeout=self.browser_launch_timeout
                    )
                    fact_logger.logger.debug("✅ Successfully connected to Railway Browserless")

                except Exception as browserless_error:
                    fact_logger.logger.warning(
                        f"❌ Railway Browserless connection failed: {browserless_error}"
                    )
                    fact_logger.logger.info("🔄 Falling back to local browser")
                    browser = None

            # Fallback to local browser if Railway connection fails
            if not browser:
                fact_logger.logger.info("🚀 Launching local browser")
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-web-security",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=VizDisplayCompositor"
                    ]
                )
                fact_logger.logger.debug("✅ Local browser launched successfully")

            # Create page with optimizations
            page = await browser.new_page()
            await self._configure_page_optimizations(page)

            # Navigate to page
            fact_logger.logger.debug(f"Navigating to: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)

            # Wait for content to stabilize
            await asyncio.sleep(self.load_wait_time)

            # Extract structured content
            content = await self._extract_structured_content(page)

            if content and len(content.strip()) > 100:
                # Clean content
                content = self._clean_content(content)
                fact_logger.logger.debug(
                    f"Extraction successful: {len(content)} chars"
                )
                return content
            else:
                fact_logger.logger.warning("Extraction yielded insufficient content")
                return ""

        except Exception as e:
            fact_logger.logger.error(f"Content extraction failed: {e}")
            return ""

        finally:
            # Clean up resources
            if page:
                try:
                    await asyncio.wait_for(page.close(), timeout=5.0)
                except Exception as e:
                    fact_logger.logger.debug(f"Page close error (non-critical): {e}")

            if browser:
                try:
                    await asyncio.wait_for(browser.close(), timeout=5.0)
                except Exception as e:
                    fact_logger.logger.debug(f"Browser close error (non-critical): {e}")

            if playwright:
                try:
                    await playwright.stop()
                except Exception as e:
                    fact_logger.logger.debug(f"Playwright stop error (non-critical): {e}")

    async def _configure_page_optimizations(self, page: Page):
        """
        Configure page with Railway Browserless optimizations
        - Block ads and trackers
        - Speed up animations
        - Set realistic headers
        """
        try:
            # Set realistic headers
            await page.set_extra_http_headers({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate, br",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            })

            # Block unnecessary resources
            await page.route("**/*", self._block_resources)

            # Inject optimization scripts
            await page.add_init_script("""
                // Disable image loading for speed
                Object.defineProperty(HTMLImageElement.prototype, 'src', {
                    set: function() { /* blocked */ },
                    get: function() { return ''; }
                });

                // Speed up animations
                document.addEventListener('DOMContentLoaded', function() {
                    const style = document.createElement('style');
                    style.textContent = `
                        *, *::before, *::after {
                            animation-duration: 0.01ms !important;
                            animation-delay: -0.01ms !important;
                            transition-duration: 0.01ms !important;
                            transition-delay: -0.01ms !important;
                        }
                    `;
                    document.head.appendChild(style);
                });

                // Disable popups
                window.alert = () => {};
                window.confirm = () => true;
                window.prompt = () => '';
            """)

        except Exception as e:
            fact_logger.logger.warning(f"Page configuration partially failed: {e}")

    async def _block_resources(self, route):
        """
        Block unnecessary resources for faster loading
        - Images, media, fonts, stylesheets
        - Tracking and advertising domains
        """
        resource_type = route.request.resource_type
        url = route.request.url

        # Block resource types that slow down scraping
        if resource_type in ['image', 'media', 'font', 'stylesheet']:
            await route.abort()
        # Block known tracking and ad domains
        elif any(domain in url for domain in [
            'google-analytics', 'googletagmanager', 'facebook.com',
            'doubleclick', 'adsystem', 'amazon-adsystem', 'googlesyndication',
            'chartbeat', 'quantserve', 'scorecardresearch'
        ]):
            await route.abort()
        else:
            await route.continue_()

    async def _extract_structured_content(self, page: Page) -> str:
        """
        Extract content while preserving structure (headings, paragraphs)
        Returns markdown-style formatted text
        """
        try:
            fact_logger.logger.debug("Extracting structured content")

            content_data = await page.evaluate("""
                () => {
                    // Convert HTML to structured text preserving headings and paragraphs
                    function htmlToStructuredText(element, level = 0) {
                        if (!element) return '';

                        let result = '';

                        // Handle text nodes
                        if (element.nodeType === Node.TEXT_NODE) {
                            const text = element.textContent.trim();
                            return text ? text + ' ' : '';
                        }

                        // Handle element nodes
                        if (element.nodeType === Node.ELEMENT_NODE) {
                            const tagName = element.tagName.toLowerCase();

                            // Skip non-content elements
                            if (['script', 'style', 'noscript', 'head', 'meta', 'link'].includes(tagName)) {
                                return '';
                            }

                            // Handle different content elements
                            switch (tagName) {
                                case 'h1':
                                case 'h2':
                                case 'h3':
                                case 'h4':
                                case 'h5':
                                case 'h6':
                                    const headingText = element.textContent.trim();
                                    if (headingText) {
                                        const headingLevel = parseInt(tagName[1]);
                                        const prefix = '#'.repeat(headingLevel);
                                        result += '\\n\\n' + prefix + ' ' + headingText + '\\n';
                                    }
                                    break;

                                case 'p':
                                    const pText = element.textContent.trim();
                                    if (pText && pText.length > 20) {
                                        result += '\\n' + pText + '\\n';
                                    }
                                    break;

                                case 'div':
                                case 'section':
                                case 'article':
                                    for (let child of element.childNodes) {
                                        result += htmlToStructuredText(child, level + 1);
                                    }
                                    break;

                                case 'li':
                                    const liText = element.textContent.trim();
                                    if (liText && liText.length > 10) {
                                        result += '\\n• ' + liText + '\\n';
                                    }
                                    break;

                                case 'strong':
                                case 'b':
                                    const strongText = element.textContent.trim();
                                    if (strongText) {
                                        result += '**' + strongText + '**';
                                    }
                                    break;

                                case 'em':
                                case 'i':
                                    const emText = element.textContent.trim();
                                    if (emText) {
                                        result += '*' + emText + '*';
                                    }
                                    break;

                                default:
                                    for (let child of element.childNodes) {
                                        result += htmlToStructuredText(child, level + 1);
                                    }
                                    break;
                            }
                        }

                        return result;
                    }

                    // Try to find main content container
                    const mainSelectors = [
                        'main',
                        'article',
                        '[role="main"]',
                        '.main-content',
                        '.content',
                        '.article-content',
                        '.post-content',
                        '#content',
                        '#main'
                    ];

                    let bestContent = '';
                    let bestScore = 0;

                    for (const selector of mainSelectors) {
                        const element = document.querySelector(selector);
                        if (element) {
                            const clone = element.cloneNode(true);

                            // Remove unwanted elements
                            const unwantedElements = clone.querySelectorAll(`
                                nav, footer, header, aside,
                                .sidebar, .navigation, .nav, .menu,
                                .cookie, .popup, .modal, .advertisement, .ad,
                                .social-share, .comments,
                                [role="navigation"], [role="banner"], [role="contentinfo"],
                                script, style, noscript
                            `);
                            unwantedElements.forEach(el => el.remove());

                            const structuredText = htmlToStructuredText(clone);

                            // Score based on content quality
                            const headingCount = (structuredText.match(/^#+\\s/gm) || []).length;
                            const paragraphCount = (structuredText.match(/\\n[^\\n#•].+\\n/g) || []).length;
                            const wordCount = structuredText.split(/\\s+/).filter(w => w.length > 0).length;

                            let score = 0;
                            score += headingCount * 10;
                            score += paragraphCount * 5;
                            score += Math.min(wordCount, 500);

                            if (score > bestScore && structuredText.length > 200) {
                                bestScore = score;
                                bestContent = structuredText;
                            }
                        }
                    }

                    // Fallback: extract headings and following paragraphs
                    if (!bestContent || bestContent.length < 300) {
                        const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
                        let fallbackContent = '';

                        for (const heading of headings) {
                            const headingText = heading.textContent.trim();
                            if (headingText && headingText.length > 5) {
                                const headingLevel = parseInt(heading.tagName[1]);
                                const prefix = '#'.repeat(headingLevel);
                                fallbackContent += '\\n\\n' + prefix + ' ' + headingText + '\\n';

                                let nextElement = heading.nextElementSibling;
                                let count = 0;

                                while (nextElement && count < 3) {
                                    if (nextElement.tagName === 'P') {
                                        const pText = nextElement.textContent.trim();
                                        if (pText.length > 30) {
                                            fallbackContent += pText + '\\n\\n';
                                            count++;
                                        }
                                    }
                                    nextElement = nextElement.nextElementSibling;
                                }
                            }
                        }

                        if (fallbackContent.length > bestContent.length) {
                            bestContent = fallbackContent;
                        }
                    }

                    return {
                        content: bestContent,
                        contentLength: bestContent.length,
                        headingCount: (bestContent.match(/^#+\\s/gm) || []).length,
                        wordCount: bestContent.split(/\\s+/).filter(w => w.length > 0).length
                    };
                }
            """)

            content = content_data.get('content', '').strip()

            fact_logger.logger.debug(
                "Structure extraction complete",
                extra={
                    "content_length": content_data.get('contentLength', 0),
                    "headings": content_data.get('headingCount', 0),
                    "words": content_data.get('wordCount', 0)
                }
            )

            return content

        except Exception as e:
            fact_logger.logger.error(f"Structure extraction error: {e}")
            return ""

    def _clean_content(self, content: str) -> str:
        """
        Clean extracted content while preserving structure
        Remove common web noise patterns
        """
        if not content:
            return ""

        # Remove excessive whitespace while preserving structure
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)

        # Remove common website noise
        noise_patterns = [
            r'Cookie.*?(?=\n|$)',
            r'Privacy Policy.*?(?=\n|$)',
            r'Terms.*?Service.*?(?=\n|$)',
            r'Subscribe.*?newsletter.*?(?=\n|$)',
            r'Follow us.*?(?=\n|$)',
            r'Download.*?app.*?(?=\n|$)',
            r'Advertisement\n',
            r'Skip to.*?content',
            r'Accept.*?cookies.*?(?=\n|$)',
            r'Back to top.*?(?=\n|$)',
        ]

        for pattern in noise_patterns:
            content = re.sub(pattern, '', content, flags=re.IGNORECASE)

        # Final cleanup
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        content = content.strip()

        return content

    def get_stats(self) -> Dict:
        """Return scraping statistics"""
        return self.stats.copy()