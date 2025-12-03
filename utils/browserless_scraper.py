# utils/browserless_scraper.py
"""
✅ FIXED Railway Browserless Scraper with Persistent Sessions & Replica Support

KEY FEATURES:
- ✅ Proper Railway Browserless connection using chromium.connect()
- ✅ Persistent browser sessions (browsers stay open during run)
- ✅ Support for Railway replicas with load distribution
- ✅ Browser pooling for connection reuse
- ✅ Fallback to local Playwright if Railway unavailable
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
    ✅ OPTIMIZED: Railway Browserless scraper with persistent sessions
    """

    def __init__(self, config):
        self.config = config

        # ✅ Railway Browserless configuration
        self.is_railway = os.getenv('RAILWAY_ENVIRONMENT') is not None
        self.browserless_endpoint = os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT_PRIVATE') or os.getenv('BROWSER_PLAYWRIGHT_ENDPOINT')
        self.browserless_token = os.getenv('BROWSER_TOKEN')

        # ✅ NEW: Support for Railway replicas
        self.replica_id = os.getenv('RAILWAY_REPLICA_ID', '0')

        # ✅ NEW: Browser pool for persistent sessions
        self.max_concurrent = 10  # Number of concurrent browsers
        self.playwright = None
        self.browser_pool: List[Browser] = []
        self.current_browser_index = 0
        self.session_active = False
        self._session_lock = asyncio.Lock()

        # Timeouts
        self.default_timeout = 5000  # 5 seconds
        self.slow_timeout = 10000     # 10 seconds
        self.browser_launch_timeout = 10000

        # Domain-specific timeouts
        self.domain_timeouts = {
            'nytimes.com': 10000,
            'washingtonpost.com': 10000,
            'wsj.com': 10000,
            'forbes.com': 10000,
        }

        # Timing
        self.load_wait_time = 2.0
        self.interaction_delay = 0.5

        # Stats tracking
        self.stats = {
            "total_scraped": 0,
            "successful_scrapes": 0,
            "failed_scrapes": 0,
            "avg_scrape_time": 0.0,
            "total_processing_time": 0.0,
            "browser_reuses": 0,
            "railway_browserless": bool(self.browserless_endpoint),
            "replica_id": self.replica_id,
        }

        if self.browserless_endpoint:
            fact_logger.logger.info(f"🚂 Railway Browserless endpoint configured: {self.browserless_endpoint[:50]}...")
            fact_logger.logger.info(f"🔢 Running on replica: {self.replica_id}")
        else:
            fact_logger.logger.info("🔧 Local Playwright mode")

        fact_logger.log_component_start(
            "FactCheckScraper",
            browserless=bool(self.browserless_endpoint),
            replica_id=self.replica_id,
            browser_pool_size=self.max_concurrent
        )

    async def scrape_urls_for_facts(self, urls: List[str]) -> Dict[str, str]:
        """
        ✅ OPTIMIZED: Scrape multiple URLs with persistent browser sessions

        Args:
            urls: List of URLs to scrape

        Returns:
            Dict mapping URL to scraped content
        """
        if not urls:
            fact_logger.logger.warning("No URLs provided for scraping")
            return {}

        fact_logger.logger.info(
            f"🚀 Starting scrape of {len(urls)} URLs with persistent browsers",
            extra={"url_count": len(urls), "replica_id": self.replica_id}
        )

        # ✅ Initialize browser pool ONCE for all URLs
        await self._initialize_browser_pool()

        try:
            # Process URLs with concurrency control
            semaphore = asyncio.Semaphore(self.max_concurrent)
            tasks = [
                self._scrape_with_semaphore(semaphore, url, i % self.max_concurrent)
                for i, url in enumerate(urls)
            ]

            results_list = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert to dict and handle exceptions
            results = {}
            for url, result in zip(urls, results_list):
                if isinstance(result, Exception):
                    fact_logger.logger.error(
                        f"❌ Scraping failed for {url}: {result}",
                        extra={"url": url, "error": str(result)}
                    )
                    results[url] = ""
                else:
                    results[url] = result

            successful = len([v for v in results.values() if v])
            self.stats["browser_reuses"] += max(0, len(urls) - self.max_concurrent)

            fact_logger.logger.info(
                f"✅ Scraping complete: {successful}/{len(urls)} successful",
                extra={
                    "successful": successful, 
                    "total": len(urls),
                    "browser_reuses": self.stats["browser_reuses"]
                }
            )

            return results

        finally:
            # ✅ IMPORTANT: Keep browsers alive for next batch
            # Browsers will be closed only when close() is called explicitly
            pass

    async def _initialize_browser_pool(self):
        """
        ✅ NEW: Initialize persistent browser pool ONCE
        """
        if self.session_active:
            return  # Already initialized

        async with self._session_lock:
            if self.session_active:
                return

            fact_logger.logger.info("🚀 Initializing browser pool...")

            # Start Playwright once
            self.playwright = await async_playwright().start()

            # Create browser pool
            for i in range(self.max_concurrent):
                try:
                    browser = await self._create_single_browser(i)
                    if browser:
                        self.browser_pool.append(browser)
                        fact_logger.logger.info(f"✅ Browser {i+1}/{self.max_concurrent} ready")
                except Exception as e:
                    fact_logger.logger.error(f"❌ Failed to create browser {i+1}: {e}")

            if len(self.browser_pool) > 0:
                self.session_active = True
                fact_logger.logger.info(
                    f"🎯 Browser pool initialized: {len(self.browser_pool)}/{self.max_concurrent} browsers ready"
                )
            else:
                raise Exception("Failed to initialize browser pool")

    async def _create_single_browser(self, browser_index: int) -> Optional[Browser]:
        """
        ✅ FIXED: Create browser using proper Railway Browserless connection
        """
        try:
            # ✅ CRITICAL: Use chromium.connect() for Railway Browserless
            if self.browserless_endpoint:
                try:
                    # Build connection URL with token
                    connect_url = self.browserless_endpoint

                    # Add token if not already in URL
                    if self.browserless_token and 'token=' not in connect_url:
                        separator = '&' if '?' in connect_url else '?'
                        connect_url = f"{connect_url}{separator}token={self.browserless_token}"
                        # Add timeout parameter (4.5 minutes = 270000 milliseconds)
                        browserless_session_timeout = 1800000
                        connect_url = f"{connect_url}&timeout={browserless_session_timeout}"

                    fact_logger.logger.info(
                        f"🔗 Browser {browser_index}: Connecting to Railway Browserless",
                        extra={"endpoint": connect_url[:50] + "...", "replica_id": self.replica_id}
                    )

                    # ✅ THIS IS THE CORRECT METHOD for Railway Browserless
                    browser = await self.playwright.chromium.connect(
                        connect_url,
                        timeout=self.browser_launch_timeout
                    )

                    fact_logger.logger.info(f"✅ Browser {browser_index} connected to Railway Browserless")
                    return browser

                except Exception as browserless_error:
                    fact_logger.logger.warning(
                        f"⚠️ Railway Browserless connection failed for browser {browser_index}: {browserless_error}"
                    )
                    fact_logger.logger.info("🔄 Falling back to local Playwright...")

            # ✅ Fallback to local Playwright
            fact_logger.logger.info(f"🔧 Browser {browser_index}: Using local Playwright")
            browser = await self.playwright.chromium.launch(
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
            return browser

        except Exception as e:
            fact_logger.logger.error(f"❌ Failed to create browser {browser_index}: {e}")
            return None

    async def _scrape_with_semaphore(self, semaphore: asyncio.Semaphore, url: str, browser_index: int) -> str:
        """
        ✅ OPTIMIZED: Scrape using persistent browser from pool
        """
        async with semaphore:
            return await self._scrape_single_url(url, browser_index)

    async def _scrape_single_url(self, url: str, browser_index: int) -> str:
        """
        ✅ OPTIMIZED: Scrape single URL using persistent browser
        """
        start_time = time.time()
        self.stats["total_scraped"] += 1

        # Select browser from pool
        if browser_index >= len(self.browser_pool):
            browser_index = 0

        browser = self.browser_pool[browser_index]
        page = None

        try:
            # Get domain-specific timeout
            domain = urlparse(url).netloc.lower()
            base_timeout = self.domain_timeouts.get(domain, self.default_timeout)
            timeout = min(base_timeout, 10000)  # Cap at 10 seconds

            fact_logger.logger.debug(
                f"🎯 Browser {browser_index}: Scraping {url}",
                extra={"url": url, "browser_index": browser_index, "timeout_ms": timeout}
            )

            # ✅ Create new page in existing browser (not a new browser!)
            page = await browser.new_page()

            # Configure page
            await self._configure_page_optimizations(page)

            # Navigate
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            await asyncio.sleep(0.5)  # Reduced from 1.0 to 0.5

            # Extract content
            content = await self._extract_structured_content(page)

            if content and len(content.strip()) > 100:
                content = self._clean_content(content)
                processing_time = time.time() - start_time

                self.stats["successful_scrapes"] += 1
                self.stats["total_processing_time"] += processing_time
                self.stats["avg_scrape_time"] = (
                    self.stats["total_processing_time"] / self.stats["total_scraped"]
                )

                fact_logger.logger.info(
                    f"✅ Successfully scraped: {url}",
                    extra={
                        "url": url,
                        "duration": processing_time,
                        "content_length": len(content),
                        "browser_index": browser_index
                    }
                )

                return content
            else:
                processing_time = time.time() - start_time
                self.stats["failed_scrapes"] += 1

                fact_logger.logger.warning(
                    f"⚠️ Insufficient content from {url}",
                    extra={"url": url, "duration": processing_time}
                )

                return ""

        except Exception as e:
            processing_time = time.time() - start_time
            self.stats["failed_scrapes"] += 1

            fact_logger.logger.error(
                f"❌ Scraping error for {url}: {e}",
                extra={"url": url, "duration": processing_time, "error": str(e)}
            )

            return ""

        finally:
            # ✅ IMPORTANT: Close page but keep browser alive!
            if page:
                try:
                    await page.close()
                except Exception as e:
                    fact_logger.logger.debug(f"Page close error (non-critical): {e}")

    async def _configure_page_optimizations(self, page: Page):
        """Configure page with optimizations"""
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
                // Disable image loading
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
            fact_logger.logger.warning(f"⚠️ Page configuration partially failed: {e}")

    async def _block_resources(self, route):
        """Block unnecessary resources for faster loading"""
        resource_type = route.request.resource_type
        url = route.request.url

        # Block resource types
        if resource_type in ['image', 'media', 'font', 'stylesheet']:
            await route.abort()
        # Block tracking domains
        elif any(domain in url for domain in [
            'google-analytics', 'googletagmanager', 'facebook.com',
            'doubleclick', 'adsystem', 'amazon-adsystem', 'googlesyndication',
            'chartbeat', 'quantserve', 'scorecardresearch'
        ]):
            await route.abort()
        else:
            await route.continue_()

    async def scrape_urls_in_batches(
        self, 
        urls: List[str], 
        batch_size: int = 5,
        progress_callback=None
    ) -> Dict[str, str]:
        """
        ✅ NEW: Scrape URLs in batches to handle large numbers of URLs

        Args:
            urls: List of all URLs to scrape
            batch_size: Number of URLs per batch (default: 5)
            progress_callback: Optional callback(current, total, results_so_far)

        Returns:
            Dict mapping URL to scraped content
        """
        if not urls:
            fact_logger.logger.warning("No URLs provided for scraping")
            return {}

        fact_logger.logger.info(
            f"🔄 Starting batch scraping of {len(urls)} URLs",
            extra={
                "total_urls": len(urls),
                "batch_size": batch_size,
                "estimated_batches": (len(urls) + batch_size - 1) // batch_size
            }
        )

        all_results = {}
        total_urls = len(urls)

        # Process URLs in batches
        for batch_num, i in enumerate(range(0, len(urls), batch_size), 1):
            batch_urls = urls[i:i + batch_size]
            total_batches = (len(urls) + batch_size - 1) // batch_size

            fact_logger.logger.info(
                f"📦 Processing batch {batch_num}/{total_batches} ({len(batch_urls)} URLs)",
                extra={
                    "batch_num": batch_num,
                    "total_batches": total_batches,
                    "batch_size": len(batch_urls)
                }
            )

            # Scrape this batch using existing method
            batch_results = await self.scrape_urls_for_facts(batch_urls)

            # Merge results
            all_results.update(batch_results)

            # Calculate progress
            completed = len(all_results)

            fact_logger.logger.info(
                f"✅ Batch {batch_num}/{total_batches} complete",
                extra={
                    "completed_urls": completed,
                    "total_urls": total_urls,
                    "progress_percent": round((completed / total_urls) * 100, 1)
                }
            )

            # Call progress callback if provided
            if progress_callback:
                try:
                    progress_callback(completed, total_urls, all_results)
                except Exception as e:
                    fact_logger.logger.warning(f"Progress callback error: {e}")

            # Small delay between batches to avoid overwhelming the system
            if i + batch_size < len(urls):  # Not the last batch
                await asyncio.sleep(2.0)

        fact_logger.logger.info(
            f"🎉 Batch scraping complete: {len(all_results)}/{total_urls} URLs scraped",
            extra={
                "successful": len([v for v in all_results.values() if v]),
                "failed": len([v for v in all_results.values() if not v]),
                "total": total_urls
            }
        )

        return all_results

    async def _extract_structured_content(self, page: Page) -> str:
        """Extract content while preserving structure"""
        try:
            fact_logger.logger.debug("Extracting structured content")

            content_data = await page.evaluate("""
                () => {
                    // Extract text while preserving structure
                    function htmlToStructuredText(element, level = 0) {
                        if (!element) return '';

                        let result = '';

                        if (element.nodeType === Node.TEXT_NODE) {
                            const text = element.textContent.trim();
                            return text ? text + ' ' : '';
                        }

                        if (element.nodeType === Node.ELEMENT_NODE) {
                            const tagName = element.tagName.toLowerCase();

                            if (['script', 'style', 'noscript', 'head', 'meta', 'link'].includes(tagName)) {
                                return '';
                            }

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

                                default:
                                    for (let child of element.childNodes) {
                                        result += htmlToStructuredText(child, level + 1);
                                    }
                                    break;
                            }
                        }

                        return result;
                    }

                    // Try main content selectors
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

                    return bestContent;
                }
            """)

            content = content_data if content_data else ""

            fact_logger.logger.debug(
                "Structure extraction complete",
                extra={"content_length": len(content)}
            )

            return content

        except Exception as e:
            fact_logger.logger.error(f"❌ Structure extraction error: {e}")
            return ""

    def _clean_content(self, content: str) -> str:
        """Clean extracted content"""
        if not content:
            return ""

        # Remove excessive whitespace
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)

        # Remove common noise
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

    async def close(self):
        """
        ✅ NEW: Properly close browser pool and cleanup
        """
        fact_logger.logger.info("🛑 Shutting down scraper...")

        # Close all browsers in pool
        for i, browser in enumerate(self.browser_pool):
            try:
                await browser.close()
                fact_logger.logger.debug(f"✅ Closed browser {i}")
            except Exception as e:
                fact_logger.logger.debug(f"Browser close error (non-critical): {e}")

        # Stop Playwright
        if self.playwright:
            try:
                await self.playwright.stop()
                fact_logger.logger.debug("✅ Playwright stopped")
            except Exception as e:
                fact_logger.logger.debug(f"Playwright stop error (non-critical): {e}")

        self.session_active = False

        # Print stats
        if self.stats["total_scraped"] > 0:
            success_rate = (self.stats["successful_scrapes"] / self.stats["total_scraped"]) * 100
            fact_logger.logger.info(
                f"📊 Scraping stats: {self.stats['successful_scrapes']}/{self.stats['total_scraped']} "
                f"successful ({success_rate:.1f}%), {self.stats['browser_reuses']} browser reuses"
            )

        fact_logger.logger.info("✅ Scraper shutdown complete")