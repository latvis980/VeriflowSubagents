# orchestrator/key_claims_orchestrator.py
"""
Key Claims Orchestrator - WITH COMPREHENSIVE SEARCH AUDIT
Extracts and verifies ONLY the 2-3 central thesis claims from text

UPDATES:
- ✅ Tracks all raw Brave Search results
- ✅ Records filtered sources with reasoning
- ✅ Records credible sources with tier assignments
- ✅ Saves comprehensive audit file

Pipeline:
1. Extract 2-3 key claims (central thesis statements)
2. Generate search queries for each key claim
3. Execute web searches via Brave → AUDIT: Track all raw results
4. Filter results by source credibility → AUDIT: Track filtered + credible
5. Scrape credible sources → AUDIT: Track scrape success/failure
6. Verify each key claim against sources
7. Generate detailed verification report
8. Save comprehensive search audit → NEW
"""

from langsmith import traceable
import time
import asyncio
from typing import List, Dict, Any, Optional

from utils.logger import fact_logger
from utils.langsmith_config import langsmith_config
from utils.file_manager import FileManager
from utils.job_manager import job_manager
from utils.browserless_scraper import FactCheckScraper
from utils.brave_searcher import BraveSearcher

# Import key claims extractor
from agents.key_claims_extractor import KeyClaimsExtractor, ContentLocation

# Import existing agents
from agents.fact_checker import FactChecker, FactCheckResult
from agents.query_generator import QueryGenerator
from agents.credibility_filter import CredibilityFilter
from agents.highlighter import Highlighter

# NEW: Import search audit utilities
from utils.search_audit_builder import (
    build_session_search_audit,
    build_fact_search_audit,
    build_query_audit,
    save_search_audit,
    upload_search_audit_to_r2
)


class KeyClaimsOrchestrator:
    """
    Orchestrator for key claims extraction and verification

    Extracts only 2-3 central thesis claims and verifies them thoroughly.

    NEW: Comprehensive search audit tracking
    """

    def __init__(self, config):
        self.config = config

        # Initialize agents
        self.extractor = KeyClaimsExtractor(config)
        self.query_generator = QueryGenerator(config)
        self.searcher = BraveSearcher(config, max_results=5)
        self.credibility_filter = CredibilityFilter(config, min_credibility_score=0.70)
        self.scraper = FactCheckScraper(config)
        self.highlighter = Highlighter(config)
        self.checker = FactChecker(config)
        self.file_manager = FileManager()

        # Configuration
        self.max_sources_per_claim = 15  # More sources per claim since fewer claims

        # NEW: Initialize R2 uploader for audit upload
        try:
            from utils.r2_uploader import R2Uploader
            self.r2_uploader = R2Uploader()
            self.r2_enabled = True
            fact_logger.logger.info("✅ R2 uploader initialized for search audits")
        except Exception as e:
            self.r2_enabled = False
            fact_logger.logger.warning(f"⚠️ R2 not available for audits: {e}")

        fact_logger.log_component_start(
            "KeyClaimsOrchestrator",
            max_sources_per_claim=self.max_sources_per_claim
        )

    def _check_cancellation(self, job_id: str):
        """Check if job has been cancelled"""
        if job_manager.is_cancelled(job_id):
            raise Exception("Job cancelled by user")

    @traceable(
        name="key_claims_verification",
        run_type="chain",
        tags=["key-claims", "thesis-verification", "search-audit"]
    )
    async def process_with_progress(self, text_content: str, job_id: str) -> dict:
        """
        Complete key claims verification pipeline with search audit
        """
        session_id = self.file_manager.create_session()
        start_time = time.time()

        # NEW: Initialize session search audit
        session_audit = None

        try:
            # Step 1: Extract Key Claims
            job_manager.add_progress(job_id, "📄 Extracting key claims from text...")
            self._check_cancellation(job_id)

            # Prepare parsed content for extractor
            parsed_content = {
                'text': text_content,
                'links': [],
                'format': 'plain_text'
            }

            claims, all_sources, content_location = await self.extractor.extract(parsed_content)

            if not claims:
                job_manager.add_progress(job_id, "⚠️ No key claims found")
                return {
                    "success": True,
                    "session_id": session_id,
                    "claims": [],
                    "summary": {"message": "No key claims identified"},
                    "processing_time": time.time() - start_time
                }

            job_manager.add_progress(job_id, f"✅ Found {len(claims)} key claims")

            # NEW: Initialize session audit with content location
            session_audit = build_session_search_audit(
                session_id=session_id,
                pipeline_type="key_claims",
                content_country=content_location.country if content_location else "international",
                content_language=content_location.language if content_location else "english"
            )

            # Step 2: Generate Search Queries
            job_manager.add_progress(job_id, "🔍 Generating search queries...")
            self._check_cancellation(job_id)

            all_queries_by_claim = {}
            for claim in claims:
                # Create fact-like object for query generator
                fact_like = type('Fact', (), {
                    'id': claim.id,
                    'statement': claim.statement
                })()

                queries = await self.query_generator.generate_queries(
                    fact_like,
                    content_location=content_location
                )
                all_queries_by_claim[claim.id] = queries

            total_queries = sum(len(q.all_queries) for q in all_queries_by_claim.values())
            job_manager.add_progress(job_id, f"✅ Generated {total_queries} queries")

            # Step 3: Execute Searches
            job_manager.add_progress(job_id, "🌐 Searching the web...")
            self._check_cancellation(job_id)

            search_results_by_claim = {}
            query_audits_by_claim = {}  # NEW: Track query audits per claim
            total_results = 0

            for claim in claims:
                queries = all_queries_by_claim[claim.id]
                search_results = await self.searcher.search_multiple(
                    queries=queries.all_queries,
                    search_depth="advanced",
                    max_concurrent=3
                )
                search_results_by_claim[claim.id] = search_results

                # Build query audits for this claim
                # SIMPLIFIED: No need to distinguish query types - AI handles language detection
                claim_query_audits = []
                for query, brave_results in search_results.items():
                    qa = build_query_audit(
                        query=query,
                        brave_results=brave_results,
                        query_type="search",  # Simplified - just "search"
                        language=queries.local_language_used or "en"
                    )
                    claim_query_audits.append(qa)
                    total_results += len(brave_results.results)

                query_audits_by_claim[claim.id] = claim_query_audits

            job_manager.add_progress(job_id, f"📊 Found {total_results} potential sources")

            # Step 4: Filter by Credibility
            job_manager.add_progress(job_id, "🏆 Filtering sources by credibility...")
            self._check_cancellation(job_id)

            credible_urls_by_claim = {}
            source_metadata_by_claim = {}
            credibility_results_by_claim = {}  # NEW: Store full credibility results

            for claim in claims:
                all_results_for_claim = []
                for query, results in search_results_by_claim[claim.id].items():
                    all_results_for_claim.extend(results.results)

                if not all_results_for_claim:
                    credible_urls_by_claim[claim.id] = []
                    source_metadata_by_claim[claim.id] = {}
                    credibility_results_by_claim[claim.id] = None
                    continue

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

                # Store metadata for tier info
                source_metadata_by_claim[claim.id] = credibility_results.get_source_metadata_dict()

            total_credible = sum(len(urls) for urls in credible_urls_by_claim.values())
            job_manager.add_progress(job_id, f"✅ Found {total_credible} credible sources")

            # Step 5: Scrape Sources
            job_manager.add_progress(job_id, f"🌐 Scraping {total_credible} credible sources...")
            self._check_cancellation(job_id)

            scraped_content_by_claim = {}
            scraped_urls_by_claim = {}  # NEW: Track successfully scraped URLs
            scrape_errors_by_claim = {}  # NEW: Track scrape errors

            for claim in claims:
                urls_to_scrape = credible_urls_by_claim.get(claim.id, [])
                if urls_to_scrape:
                    scraped_content = await self.scraper.scrape_urls_for_facts(urls_to_scrape)
                    scraped_content_by_claim[claim.id] = scraped_content

                    # NEW: Track which URLs were successfully scraped
                    scraped_urls_by_claim[claim.id] = [
                        url for url, content in scraped_content.items()
                        if content  # Non-empty content means success
                    ]
                    scrape_errors_by_claim[claim.id] = {
                        url: "Scrape failed or empty content"
                        for url in urls_to_scrape
                        if url not in scraped_urls_by_claim[claim.id]
                    }

            job_manager.add_progress(job_id, "✅ Scraping complete")

            # NEW: Build claim search audits BEFORE verification
            for claim in claims:
                claim_audit = build_fact_search_audit(
                    fact_id=claim.id,
                    fact_statement=claim.statement,
                    query_audits=query_audits_by_claim.get(claim.id, []),
                    credibility_results=credibility_results_by_claim.get(claim.id),
                    scraped_urls=scraped_urls_by_claim.get(claim.id, []),
                    scrape_errors=scrape_errors_by_claim.get(claim.id, {})
                )
                session_audit.add_fact_audit(claim_audit)

            # Step 6: Extract Excerpts and Verify Each Key Claim
            job_manager.add_progress(job_id, f"⚖️ Verifying {len(claims)} key claims...")
            self._check_cancellation(job_id)

            results = []
            for claim in claims:
                scraped_content = scraped_content_by_claim.get(claim.id, {})
                source_metadata = source_metadata_by_claim.get(claim.id, {})

                if not scraped_content or not any(scraped_content.values()):
                    result = FactCheckResult(
                        fact_id=claim.id,
                        statement=claim.statement,
                        match_score=0.0,
                        confidence=0.0,
                        report="Unable to verify - no credible sources found. Web search did not return any Tier 1 or Tier 2 sources for this key claim."
                    )
                    results.append(result)
                    job_manager.add_progress(job_id, f"⚠️ {claim.id}: No sources")
                    continue

                # Extract relevant excerpts
                fact_like = type('Fact', (), {
                    'id': claim.id,
                    'statement': claim.statement
                })()

                excerpts = await self.highlighter.highlight(
                    fact=fact_like,
                    scraped_content=scraped_content
                )

                # Check the claim
                result = await self.checker.check_fact(
                    fact=fact_like,
                    excerpts=excerpts,
                    source_metadata=source_metadata
                )

                results.append(result)

                score_emoji = "✅" if result.match_score >= 0.9 else "⚠️" if result.match_score >= 0.7 else "❌"
                job_manager.add_progress(
                    job_id,
                    f"{score_emoji} {claim.id}: {result.match_score:.0%} verified"
                )

            # Step 7: Generate Summary
            processing_time = time.time() - start_time

            verified = len([r for r in results if r.match_score >= 0.9])
            partial = len([r for r in results if 0.7 <= r.match_score < 0.9])
            unverified = len([r for r in results if r.match_score < 0.7])

            summary = {
                "total_claims": len(claims),
                "verified": verified,
                "partial": partial,
                "unverified": unverified,
                "average_score": sum(r.match_score for r in results) / len(results) if results else 0
            }

            # NEW: Save search audit
            job_manager.add_progress(job_id, "📋 Saving search audit...")

            audit_file_path = save_search_audit(
                session_audit=session_audit,
                file_manager=self.file_manager,
                session_id=session_id,
                filename="search_audit.json"
            )

            # NEW: Upload audit to R2 if available
            audit_r2_url = None
            if self.r2_enabled:
                audit_r2_url = await upload_search_audit_to_r2(
                    session_audit=session_audit,
                    session_id=session_id,
                    r2_uploader=self.r2_uploader,
                    pipeline_type="key-claims"
                )

            job_manager.add_progress(job_id, f"✅ Complete in {processing_time:.1f}s")

            return {
                "success": True,
                "session_id": session_id,
                "claims": [
                    {
                        "id": r.fact_id,
                        "statement": r.statement,
                        "match_score": r.match_score,
                        "confidence": r.confidence,
                        "report": r.report,
                        "tier_breakdown": r.tier_breakdown
                    }
                    for r in results
                ],
                "summary": summary,
                "processing_time": processing_time,
                "methodology": "key_claims_verification",
                "content_location": {
                    "country": content_location.country,
                    "language": content_location.language
                } if content_location else None,
                "statistics": {
                    "claims_extracted": len(claims),
                    "queries_generated": total_queries,
                    "raw_results_found": total_results,
                    "credible_sources": total_credible,
                    "claims_verified": len(results)
                },
                # NEW: Audit information
                "audit": {
                    "local_path": audit_file_path,
                    "r2_url": audit_r2_url,
                    "summary": {
                        "total_raw_results": session_audit.total_raw_results,
                        "total_credible": session_audit.total_credible_sources,
                        "total_filtered": session_audit.total_filtered_sources,
                        "tier_breakdown": {
                            "tier1": session_audit.total_tier1,
                            "tier2": session_audit.total_tier2,
                            "tier3_filtered": session_audit.total_tier3_filtered
                        }
                    }
                }
            }

        except Exception as e:
            error_msg = str(e)
            if "cancelled" in error_msg.lower():
                job_manager.add_progress(job_id, "🛑 Verification cancelled")
                return {
                    "success": False,
                    "session_id": session_id,
                    "error": "Cancelled by user",
                    "processing_time": time.time() - start_time
                }

            fact_logger.logger.error(f"Key claims orchestrator error: {e}")
            job_manager.add_progress(job_id, f"❌ Error: {error_msg}")

            # NEW: Try to save partial audit even on error
            if session_audit and session_audit.total_facts > 0:
                try:
                    save_search_audit(
                        session_audit=session_audit,
                        file_manager=self.file_manager,
                        session_id=session_id,
                        filename="search_audit_partial.json"
                    )
                except:
                    pass  # Don't fail on audit save error

            return {
                "success": False,
                "session_id": session_id,
                "error": error_msg,
                "processing_time": time.time() - start_time
            }