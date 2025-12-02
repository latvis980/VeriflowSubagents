# orchestrator/key_claims_orchestrator.py
"""
Key Claims Orchestrator
Extracts and verifies ONLY the 2-3 central thesis claims from text

PURPOSE: Find and thoroughly verify the MAIN ARGUMENTS of an article
- Not every fact, just the key claims the article was written to prove
- More thorough verification per claim (since we're checking fewer claims)

Pipeline:
1. Extract 2-3 key claims (central thesis statements)
2. Generate search queries for each key claim
3. Execute web searches via Tavily
4. Filter results by source credibility
5. Scrape credible sources
6. Verify each key claim against sources
7. Generate detailed verification report

DIFFERENCE FROM WebSearchOrchestrator:
- Extracts 2-3 KEY CLAIMS vs ALL facts
- More thorough verification per claim
- Focuses on thesis statements, not supporting details
"""

from langsmith import traceable
import time
import asyncio
from typing import List, Dict, Any, Optional

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.file_manager import FileManager
from utils.job_manager import job_manager

# Import key claims extractor (new)
from agents.key_claims_extractor import KeyClaimsExtractor, ContentLocation

# Import existing agents (reuse from web search pipeline)
from agents.browserless_scraper import FactCheckScraper
from agents.fact_checker import FactChecker
from agents.query_generator import QueryGenerator
from agents.tavily_searcher import TavilySearcher
from agents.credibility_filter import CredibilityFilter
from agents.highlighter import Highlighter


class KeyClaimsOrchestrator:
    """
    Orchestrator for key claims extraction and verification
    
    Extracts only 2-3 central thesis claims and verifies them thoroughly.
    For when you want to know: "What is this article trying to prove, and is it true?"
    """

    def __init__(self, config):
        self.config = config

        # Initialize all agents
        self.extractor = KeyClaimsExtractor(config)
        self.query_generator = QueryGenerator(config)
        self.searcher = TavilySearcher(config, max_results=7)  # More results per claim
        self.credibility_filter = CredibilityFilter(config, min_credibility_score=0.70)
        self.scraper = FactCheckScraper(config)
        self.highlighter = Highlighter(config)
        self.checker = FactChecker(config)
        self.file_manager = FileManager()

        # Configuration - more thorough since we have fewer claims
        self.max_sources_per_claim = 15  # More sources per claim (vs 10 for regular facts)
        self.max_concurrent_scrapes = 5

        fact_logger.log_component_start(
            "KeyClaimsOrchestrator",
            max_sources_per_claim=self.max_sources_per_claim,
            max_claims=3
        )

    def _check_cancellation(self, job_id: str):
        """Check if job has been cancelled and raise exception if so"""
        job = job_manager.get_job(job_id)
        if job and job.get('status') == 'cancelled':
            raise Exception("Job cancelled by user")

    def _create_empty_result(self, session_id: str, message: str) -> dict:
        """Create an empty result for cases with no claims"""
        return {
            "success": True,
            "session_id": session_id,
            "key_claims": [],
            "summary": {"message": message},
            "processing_time": 0,
            "methodology": "key_claims_verification",
            "statistics": {}
        }

    def _generate_summary(self, results: list) -> dict:
        """Generate summary statistics from results"""
        if not results:
            return {"message": "No results to summarize"}

        scores = [r.match_score for r in results]
        return {
            "total_key_claims": len(results),
            "average_score": sum(scores) / len(scores) if scores else 0,
            "verified_count": len([r for r in results if r.match_score >= 0.9]),
            "partial_count": len([r for r in results if 0.7 <= r.match_score < 0.9]),
            "unverified_count": len([r for r in results if r.match_score < 0.7]),
            "overall_credibility": self._calculate_overall_credibility(results)
        }

    def _calculate_overall_credibility(self, results: list) -> str:
        """Calculate overall credibility assessment"""
        if not results:
            return "Unable to assess"
        
        avg_score = sum(r.match_score for r in results) / len(results)
        
        if avg_score >= 0.9:
            return "High - Key claims are well-supported"
        elif avg_score >= 0.7:
            return "Medium - Some claims need more evidence"
        elif avg_score >= 0.5:
            return "Low - Significant claims are unsupported"
        else:
            return "Very Low - Key claims appear to be false or unverifiable"

    @traceable(name="key_claims_pipeline")
    async def process(self, text_content: str, save_to_r2: bool = True) -> dict:
        """
        Process text to extract and verify key claims
        
        Args:
            text_content: Text to analyze
            save_to_r2: Whether to upload results to R2
            
        Returns:
            Complete verification results
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        try:
            # Step 1: Extract Key Claims
            parsed_input = {
                'text': text_content,
                'links': [],
                'format': 'plain_text'
            }

            claims, _, content_location = await self.extractor.extract(parsed_input)

            if not claims:
                return self._create_empty_result(session_id, "No key claims identified in text")

            fact_logger.logger.info(f"🎯 Extracted {len(claims)} key claims for verification")

            # Step 2: Generate Search Queries
            all_queries_by_claim = {}
            for claim in claims:
                # Create a Fact-like object for query generator compatibility
                fact_like = type('Fact', (), {
                    'id': claim.id,
                    'statement': claim.statement,
                    'original_text': claim.original_text
                })()
                
                queries = await self.query_generator.generate_queries(
                    fact_like,
                    context="",
                    content_location=content_location
                )
                all_queries_by_claim[claim.id] = queries

            # Step 3: Execute Web Searches
            search_results_by_claim = {}
            for claim in claims:
                queries = all_queries_by_claim[claim.id]
                search_results = await self.searcher.search_multiple(
                    queries=queries.all_queries,
                    search_depth="advanced",
                    max_concurrent=3
                )
                search_results_by_claim[claim.id] = search_results

            # Step 4: Filter by Credibility
            credible_urls_by_claim = {}
            for claim in claims:
                all_results_for_claim = []
                for query, results in search_results_by_claim[claim.id].items():
                    all_results_for_claim.extend(results.results)

                if not all_results_for_claim:
                    credible_urls_by_claim[claim.id] = []
                    continue

                # Create Fact-like object for credibility filter
                fact_like = type('Fact', (), {
                    'id': claim.id,
                    'statement': claim.statement
                })()

                credibility_results = await self.credibility_filter.evaluate_sources(
                    fact=fact_like,
                    search_results=all_results_for_claim
                )

                credible_urls = credibility_results.get_top_sources(self.max_sources_per_claim)
                credible_urls_by_claim[claim.id] = [s.url for s in credible_urls]

            # Step 5: Scrape Sources
            scraped_content_by_claim = {}
            for claim in claims:
                urls_to_scrape = credible_urls_by_claim.get(claim.id, [])
                if urls_to_scrape:
                    scraped_content = await self.scraper.scrape_urls_for_facts(urls_to_scrape)
                    scraped_content_by_claim[claim.id] = scraped_content

            # Step 6: Verify Each Key Claim
            results = []
            for claim in claims:
                scraped_content = scraped_content_by_claim.get(claim.id, {})

                if not scraped_content or not any(scraped_content.values()):
                    from agents.fact_checker import FactCheckResult
                    result = FactCheckResult(
                        fact_id=claim.id,
                        statement=claim.statement,
                        match_score=0.0,
                        assessment="Unable to verify - no credible sources found",
                        discrepancies="No sources available for verification",
                        confidence=0.0,
                        reasoning="Web search did not yield credible sources for this key claim"
                    )
                    results.append(result)
                    continue

                # Create Fact-like object for highlighter and checker
                fact_like = type('Fact', (), {
                    'id': claim.id,
                    'statement': claim.statement,
                    'original_text': claim.original_text
                })()

                # Extract relevant excerpts
                excerpts = await self.highlighter.highlight(fact_like, scraped_content)
                
                # Verify claim against excerpts
                check_result = await self.checker.check_fact(fact_like, excerpts)
                results.append(check_result)

            # Sort by match score (lowest first to surface issues)
            results.sort(key=lambda x: x.match_score)

            # Save results
            all_scraped_content = {}
            for claim_scraped in scraped_content_by_claim.values():
                all_scraped_content.update(claim_scraped)

            # Convert claims to Fact-like objects for file manager
            facts_for_save = [
                type('Fact', (), {
                    'id': c.id,
                    'statement': c.statement,
                    'original_text': c.original_text,
                    'sources': c.sources,
                    'confidence': c.confidence
                })()
                for c in claims
            ]

            upload_result = self.file_manager.save_session_content(
                session_id,
                all_scraped_content,
                facts_for_save,
                upload_to_r2=save_to_r2,
                queries_by_fact=all_queries_by_claim
            )

            summary = self._generate_summary(results)
            duration = time.time() - start_time

            return {
                "success": True,
                "session_id": session_id,
                "key_claims": [r.dict() for r in results],
                "summary": summary,
                "processing_time": duration,
                "methodology": "key_claims_verification",
                "content_location": {
                    "country": content_location.country,
                    "language": content_location.language,
                    "confidence": content_location.confidence
                },
                "statistics": {
                    "claims_extracted": len(claims),
                    "claims_verified": len(results),
                    "sources_scraped": len(all_scraped_content),
                    "successful_scrapes": len([c for c in all_scraped_content.values() if c])
                },
                "r2_upload": {
                    "success": upload_result.get('success', False) if upload_result else False,
                    "url": upload_result.get('url') if upload_result else None,
                    "filename": upload_result.get('filename') if upload_result else None
                }
            }

        except Exception as e:
            fact_logger.log_component_error("KeyClaimsOrchestrator", e)
            raise

    async def process_with_progress(self, text_content: str, job_id: str) -> dict:
        """
        Process with real-time progress updates (for web interface)
        
        Args:
            text_content: Text to analyze
            job_id: Job ID for progress tracking
            
        Returns:
            Complete key claims verification results
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        try:
            # Step 1: Extract Key Claims
            job_manager.add_progress(job_id, "🎯 Extracting key claims from text...")
            self._check_cancellation(job_id)

            parsed_input = {
                'text': text_content,
                'links': [],
                'format': 'plain_text'
            }

            claims, _, content_location = await self.extractor.extract(parsed_input)

            if not claims:
                job_manager.add_progress(job_id, "⚠️ No key claims identified")
                return self._create_empty_result(session_id, "No key claims identified in text")

            job_manager.add_progress(
                job_id, 
                f"✅ Identified {len(claims)} key claim(s) to verify"
            )

            # Show the key claims
            for i, claim in enumerate(claims, 1):
                claim_preview = claim.statement[:80] + "..." if len(claim.statement) > 80 else claim.statement
                job_manager.add_progress(job_id, f"   📌 Claim {i}: \"{claim_preview}\"")

            # Log detected location
            if content_location.country != "international":
                if content_location.language != "english":
                    job_manager.add_progress(
                        job_id,
                        f"🌍 Detected location: {content_location.country} ({content_location.language})"
                    )
                else:
                    job_manager.add_progress(
                        job_id,
                        f"🌍 Detected location: {content_location.country}"
                    )

            # Step 2: Generate Search Queries
            job_manager.add_progress(job_id, "🔍 Generating search queries for key claims...")
            self._check_cancellation(job_id)

            all_queries_by_claim = {}
            local_language_used = None

            for claim in claims:
                # Create a Fact-like object for query generator compatibility
                fact_like = type('Fact', (), {
                    'id': claim.id,
                    'statement': claim.statement,
                    'original_text': claim.original_text
                })()

                queries = await self.query_generator.generate_queries(
                    fact_like,
                    context="",
                    content_location=content_location
                )
                all_queries_by_claim[claim.id] = queries

                if queries.local_language_used:
                    local_language_used = queries.local_language_used

            total_queries = sum(len(q.all_queries) for q in all_queries_by_claim.values())

            if local_language_used:
                job_manager.add_progress(
                    job_id,
                    f"✅ Generated {total_queries} queries (includes {local_language_used} queries)"
                )
            else:
                job_manager.add_progress(job_id, f"✅ Generated {total_queries} search queries")

            # Step 3: Execute Web Searches
            job_manager.add_progress(job_id, "🌐 Searching the web for evidence...")
            self._check_cancellation(job_id)

            search_results_by_claim = {}
            for i, claim in enumerate(claims, 1):
                job_manager.add_progress(
                    job_id,
                    f"🔎 Searching for claim {i}/{len(claims)}: \"{claim.statement[:50]}...\""
                )

                queries = all_queries_by_claim[claim.id]
                search_results = await self.searcher.search_multiple(
                    queries=queries.all_queries,
                    search_depth="advanced",
                    max_concurrent=3
                )
                search_results_by_claim[claim.id] = search_results

            job_manager.add_progress(job_id, "✅ Web searches complete")

            # Step 4: Filter by Credibility
            job_manager.add_progress(job_id, "⭐ Filtering sources by credibility...")
            self._check_cancellation(job_id)

            credible_urls_by_claim = {}
            credibility_results_by_claim = {}

            for claim in claims:
                all_results_for_claim = []
                for query, results in search_results_by_claim[claim.id].items():
                    all_results_for_claim.extend(results.results)

                if not all_results_for_claim:
                    credible_urls_by_claim[claim.id] = []
                    continue

                # Create Fact-like object for credibility filter
                fact_like = type('Fact', (), {
                    'id': claim.id,
                    'statement': claim.statement
                })()

                credibility_results = await self.credibility_filter.evaluate_sources(
                    fact=fact_like,
                    search_results=all_results_for_claim
                )
                credibility_results_by_claim[claim.id] = credibility_results

                credible_urls = credibility_results.get_top_sources(self.max_sources_per_claim)
                credible_urls_by_claim[claim.id] = [s.url for s in credible_urls]

            total_credible = sum(len(urls) for urls in credible_urls_by_claim.values())
            job_manager.add_progress(job_id, f"✅ Found {total_credible} credible sources")

            # Step 5: Scrape Sources
            job_manager.add_progress(job_id, f"🌐 Scraping {total_credible} sources...")
            self._check_cancellation(job_id)

            scraped_content_by_claim = {}
            for claim in claims:
                urls_to_scrape = credible_urls_by_claim.get(claim.id, [])
                if urls_to_scrape:
                    scraped_content = await self.scraper.scrape_urls_for_facts(urls_to_scrape)
                    scraped_content_by_claim[claim.id] = scraped_content

            job_manager.add_progress(job_id, "✅ Scraping complete")

            # Step 6: Verify Key Claims (Parallel)
            job_manager.add_progress(
                job_id,
                f"⚖️ Verifying {len(claims)} key claim(s)..."
            )
            self._check_cancellation(job_id)

            async def verify_single_claim(claim, claim_index):
                """Verify a single key claim and return result"""
                try:
                    scraped_content = scraped_content_by_claim.get(claim.id, {})

                    if not scraped_content or not any(scraped_content.values()):
                        from agents.fact_checker import FactCheckResult
                        result = FactCheckResult(
                            fact_id=claim.id,
                            statement=claim.statement,
                            match_score=0.0,
                            assessment="Unable to verify - no credible sources found",
                            discrepancies="No sources available for verification",
                            confidence=0.0,
                            reasoning="Web search did not yield credible sources for this key claim"
                        )
                        job_manager.add_progress(job_id, f"⚠️ {claim.id}: No sources found")
                        return result

                    # Create Fact-like object
                    fact_like = type('Fact', (), {
                        'id': claim.id,
                        'statement': claim.statement,
                        'original_text': claim.original_text
                    })()

                    # Extract relevant excerpts
                    excerpts = await self.highlighter.highlight(fact_like, scraped_content)
                    
                    # Verify claim
                    check_result = await self.checker.check_fact(fact_like, excerpts)

                    # Progress emoji based on score
                    if check_result.match_score >= 0.9:
                        emoji = "✅"
                        status = "VERIFIED"
                    elif check_result.match_score >= 0.7:
                        emoji = "⚠️"
                        status = "PARTIAL"
                    else:
                        emoji = "❌"
                        status = "UNVERIFIED"

                    job_manager.add_progress(
                        job_id,
                        f"{emoji} {claim.id}: {status} (Score: {check_result.match_score:.2f})"
                    )

                    return check_result

                except Exception as e:
                    fact_logger.logger.error(f"❌ Error verifying {claim.id}: {e}")
                    from agents.fact_checker import FactCheckResult
                    return FactCheckResult(
                        fact_id=claim.id,
                        statement=claim.statement,
                        match_score=0.0,
                        assessment=f"Verification error: {str(e)}",
                        discrepancies="Error during verification",
                        confidence=0.0,
                        reasoning=str(e)
                    )

            # Execute all verifications in parallel
            verification_tasks = [
                verify_single_claim(claim, i)
                for i, claim in enumerate(claims, 1)
            ]

            results = await asyncio.gather(*verification_tasks, return_exceptions=False)

            # Sort by match score (lowest first to surface issues)
            results.sort(key=lambda x: x.match_score)

            job_manager.add_progress(job_id, "✅ All key claims verified")

            # Save and upload to R2
            job_manager.add_progress(job_id, "💾 Saving results...")
            self._check_cancellation(job_id)

            all_scraped_content = {}
            for claim_scraped in scraped_content_by_claim.values():
                all_scraped_content.update(claim_scraped)

            # Convert claims to Fact-like objects for file manager
            facts_for_save = [
                type('Fact', (), {
                    'id': c.id,
                    'statement': c.statement,
                    'original_text': c.original_text,
                    'sources': c.sources,
                    'confidence': c.confidence
                })()
                for c in claims
            ]

            upload_result = self.file_manager.save_session_content(
                session_id,
                all_scraped_content,
                facts_for_save,
                upload_to_r2=True,
                queries_by_fact=all_queries_by_claim
            )

            if upload_result and upload_result.get('success'):
                job_manager.add_progress(job_id, "☁️ Report uploaded to R2")
            else:
                error_msg = upload_result.get('error', 'Unknown error') if upload_result else 'Upload returned no result'
                job_manager.add_progress(job_id, f"⚠️ R2 upload failed: {error_msg}")

            summary = self._generate_summary(results)
            duration = time.time() - start_time

            # Final summary
            job_manager.add_progress(
                job_id,
                f"🎯 Key Claims Analysis Complete: {summary['overall_credibility']}"
            )

            return {
                "success": True,
                "session_id": session_id,
                "key_claims": [r.dict() for r in results],
                "summary": summary,
                "processing_time": duration,
                "methodology": "key_claims_verification",
                "content_location": {
                    "country": content_location.country,
                    "language": content_location.language,
                    "confidence": content_location.confidence
                },
                "statistics": {
                    "claims_extracted": len(claims),
                    "claims_verified": len(results),
                    "total_searches": total_queries,
                    "local_language_queries": local_language_used is not None,
                    "local_language": local_language_used,
                    "total_sources_found": sum(
                        sum(len(r.results) for r in sr.values())
                        for sr in search_results_by_claim.values()
                    ),
                    "credible_sources_identified": total_credible,
                    "sources_scraped": len(all_scraped_content),
                    "successful_scrapes": len([c for c in all_scraped_content.values() if c])
                },
                "r2_upload": {
                    "success": upload_result.get('success', False) if upload_result else False,
                    "url": upload_result.get('url') if upload_result else None,
                    "filename": upload_result.get('filename') if upload_result else None,
                    "error": upload_result.get('error') if upload_result else None
                },
                "langsmith_url": f"https://smith.langchain.com/projects/p/{langsmith_config.project_name}"
            }

        except Exception as e:
            # Handle cancellation specially
            if "cancelled" in str(e).lower():
                job_manager.add_progress(job_id, "🛑 Job cancelled")
                raise

            fact_logger.log_component_error("KeyClaimsOrchestrator", e)
            job_manager.add_progress(job_id, f"❌ Error: {str(e)}")
            raise
