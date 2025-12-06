# utils/search_audit.py
"""
Search Audit Data Models
Stores comprehensive audit trail of all Brave Search results, filtering decisions, and tier assignments

PURPOSE: Complete transparency for fact-checking pipeline
- All raw results returned by Brave Search
- Filtered out sources with reasoning
- Selected credible sources with tier assignments
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
import json


@dataclass
class RawSearchResult:
    """Single raw result from Brave Search (before filtering)"""
    url: str
    title: str
    content: str  # Preview/description
    position: int  # Position in search results (1-based)
    score: float  # Position-based relevance score
    published_date: Optional[str] = None
    query: str = ""  # The query that returned this result
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FilteredSource:
    """Source that was filtered OUT by credibility filter"""
    url: str
    title: str
    credibility_score: float
    credibility_tier: str  # "Tier 3 - Discard"
    reasoning: str  # Why it was filtered out
    query_origin: str = ""  # Which query found this source
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CredibleSource:
    """Source that passed credibility filter"""
    url: str
    title: str
    credibility_score: float
    credibility_tier: str  # "Tier 1 - Primary Authority" or "Tier 2 - Credible Secondary"
    reasoning: str  # Why it's credible
    source_name: Optional[str] = None  # Extracted publication name
    source_type: Optional[str] = None  # Website, news, etc.
    query_origin: str = ""  # Which query found this source
    was_scraped: bool = False  # Whether we successfully scraped it
    scrape_error: Optional[str] = None  # If scraping failed, why
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QueryAudit:
    """Audit trail for a single search query"""
    query: str
    query_type: str = "english"  # english, local_language, fallback
    language: str = "en"
    results_count: int = 0
    search_time_seconds: float = 0.0
    raw_results: List[RawSearchResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "language": self.language,
            "results_count": self.results_count,
            "search_time_seconds": self.search_time_seconds,
            "raw_results": [r.to_dict() for r in self.raw_results]
        }


@dataclass
class FactSearchAudit:
    """Complete audit for searching a single fact/claim"""
    fact_id: str
    fact_statement: str
    queries: List[QueryAudit] = field(default_factory=list)
    
    # All unique URLs found across all queries
    total_unique_urls: int = 0
    
    # Credibility filtering results
    credible_sources: List[CredibleSource] = field(default_factory=list)
    filtered_sources: List[FilteredSource] = field(default_factory=list)
    
    # Summary stats
    tier1_count: int = 0
    tier2_count: int = 0
    tier3_filtered_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "fact_statement": self.fact_statement,
            "queries": [q.to_dict() for q in self.queries],
            "total_unique_urls": self.total_unique_urls,
            "credibility_filtering": {
                "credible_sources": [s.to_dict() for s in self.credible_sources],
                "filtered_sources": [s.to_dict() for s in self.filtered_sources],
                "summary": {
                    "tier1_count": self.tier1_count,
                    "tier2_count": self.tier2_count,
                    "tier3_filtered_count": self.tier3_filtered_count,
                    "total_credible": self.tier1_count + self.tier2_count,
                    "total_filtered": self.tier3_filtered_count
                }
            }
        }


@dataclass
class SessionSearchAudit:
    """Complete audit for an entire fact-checking session"""
    session_id: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    pipeline_type: str = "web_search"  # web_search, key_claims, llm_output
    
    # Content location (detected language/country)
    content_country: str = "international"
    content_language: str = "english"
    
    # Per-fact audits
    fact_audits: List[FactSearchAudit] = field(default_factory=list)
    
    # Session-level summary
    total_facts: int = 0
    total_queries_executed: int = 0
    total_raw_results: int = 0
    total_unique_urls: int = 0
    total_credible_sources: int = 0
    total_filtered_sources: int = 0
    
    # Tier breakdown across all facts
    total_tier1: int = 0
    total_tier2: int = 0
    total_tier3_filtered: int = 0
    
    def add_fact_audit(self, fact_audit: FactSearchAudit):
        """Add a fact audit and update session totals"""
        self.fact_audits.append(fact_audit)
        
        # Update totals
        self.total_facts = len(self.fact_audits)
        self.total_queries_executed += len(fact_audit.queries)
        
        for query in fact_audit.queries:
            self.total_raw_results += query.results_count
            
        self.total_unique_urls += fact_audit.total_unique_urls
        self.total_credible_sources += len(fact_audit.credible_sources)
        self.total_filtered_sources += len(fact_audit.filtered_sources)
        
        self.total_tier1 += fact_audit.tier1_count
        self.total_tier2 += fact_audit.tier2_count
        self.total_tier3_filtered += fact_audit.tier3_filtered_count
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "pipeline_type": self.pipeline_type,
            "content_location": {
                "country": self.content_country,
                "language": self.content_language
            },
            "summary": {
                "total_facts": self.total_facts,
                "total_queries_executed": self.total_queries_executed,
                "total_raw_results": self.total_raw_results,
                "total_unique_urls": self.total_unique_urls,
                "total_credible_sources": self.total_credible_sources,
                "total_filtered_sources": self.total_filtered_sources,
                "tier_breakdown": {
                    "tier1_primary_authority": self.total_tier1,
                    "tier2_credible_secondary": self.total_tier2,
                    "tier3_filtered_out": self.total_tier3_filtered
                }
            },
            "fact_audits": [f.to_dict() for f in self.fact_audits]
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


# =============================================================================
# Factory Functions - Used by search_audit_builder.py
# =============================================================================

def create_raw_search_result(
    brave_result: Dict[str, Any],
    position: int,
    query: str
) -> RawSearchResult:
    """Factory function to create RawSearchResult from Brave Search response"""
    return RawSearchResult(
        url=brave_result.get('url', ''),
        title=brave_result.get('title', ''),
        content=brave_result.get('content', brave_result.get('description', '')),
        position=position,
        score=brave_result.get('score', 1.0 - (position - 1) * 0.1),
        published_date=brave_result.get('published_date'),
        query=query
    )


def create_credible_source(
    evaluation,  # SourceEvaluation from credibility_filter
    query_origin: str = ""
) -> CredibleSource:
    """Factory function to create CredibleSource from credibility evaluation"""
    return CredibleSource(
        url=evaluation.url,
        title=evaluation.title,
        credibility_score=evaluation.credibility_score,
        credibility_tier=evaluation.credibility_tier,
        reasoning=evaluation.reasoning,
        query_origin=query_origin
    )


def create_filtered_source(
    evaluation,  # SourceEvaluation from credibility_filter
    query_origin: str = ""
) -> FilteredSource:
    """Factory function to create FilteredSource from credibility evaluation"""
    return FilteredSource(
        url=evaluation.url,
        title=evaluation.title,
        credibility_score=evaluation.credibility_score,
        credibility_tier=evaluation.credibility_tier,
        reasoning=evaluation.reasoning,
        query_origin=query_origin
    )
