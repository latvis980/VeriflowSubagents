# utils/supabase_service.py
"""
Supabase Service for Media Credibility Database
Handles CRUD operations for media_credibility and propaganda_channels tables
Includes AI-powered functions for name generation and tier assignment
"""

import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger

from supabase import create_client, Client
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import json


class SupabaseService:
    """
    Service for interacting with Supabase media credibility tables
    
    Tables:
    - media_credibility: Stores MBFC ratings and AI-generated tiers
    - propaganda_channels: Stores known propaganda sources
    """
    
    def __init__(self, config=None):
        """
        Initialize Supabase client
        
        Args:
            config: Optional config object with supabase_url and supabase_key
        """
        # Get credentials from config or environment
        if config:
            self.supabase_url = getattr(config, 'supabase_url', None) or os.getenv('SUPABASE_URL')
            self.supabase_key = getattr(config, 'supabase_key', None) or os.getenv('SUPABASE_KEY')
        else:
            self.supabase_url = os.getenv('SUPABASE_URL')
            self.supabase_key = os.getenv('SUPABASE_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            logger.warning("⚠️ Supabase credentials not configured - database features disabled")
            self.client = None
            self.enabled = False
            return
        
        try:
            self.client: Client = create_client(self.supabase_url, self.supabase_key)
            self.enabled = True
            logger.info("✅ Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {e}")
            self.client = None
            self.enabled = False
        
        # Initialize LLM for AI-powered features
        openai_key = getattr(config, 'openai_api_key', None) if config else os.getenv('OPENAI_API_KEY')
        if openai_key:
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0
            ).bind(response_format={"type": "json_object"})
            self.ai_enabled = True
        else:
            self.llm = None
            self.ai_enabled = False
            logger.warning("⚠️ OpenAI not configured - AI features disabled")

    # ==========================================
    # MEDIA CREDIBILITY TABLE OPERATIONS
    # ==========================================
    
    def get_credibility_by_domain(self, domain: str) -> Optional[Dict]:
        """
        Look up a publication by domain
        
        Args:
            domain: The domain to look up (e.g., "cnn.com")
            
        Returns:
            Publication record if found, None otherwise
        """
        if not self.enabled:
            return None
        
        try:
            result = self.client.table('media_credibility') \
                .select('*') \
                .eq('domain', domain.lower()) \
                .single() \
                .execute()
            
            return result.data
        except Exception as e:
            # No record found or error
            logger.debug(f"No record found for domain {domain}: {e}")
            return None
    
    def search_credibility_by_name(self, name: str) -> List[Dict]:
        """
        Search publications by name (uses the names array)
        
        Args:
            name: Name to search for (e.g., "NYT", "New York Times")
            
        Returns:
            List of matching publications
        """
        if not self.enabled:
            return []
        
        try:
            # Use array contains operator
            result = self.client.table('media_credibility') \
                .select('*') \
                .contains('names', [name]) \
                .execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error searching by name: {e}")
            return []
    
    def upsert_credibility(self, data: Dict) -> Optional[Dict]:
        """
        Insert or update a media credibility record
        
        Args:
            data: Dictionary with publication data. Must include 'domain'.
            
        Returns:
            The upserted record, or None on failure
        """
        if not self.enabled:
            return None
        
        if 'domain' not in data:
            logger.error("❌ Domain is required for upsert")
            return None
        
        # Normalize domain
        data['domain'] = data['domain'].lower()
        
        # Update timestamp
        data['updated_at'] = datetime.utcnow().isoformat()
        
        try:
            result = self.client.table('media_credibility') \
                .upsert(data, on_conflict='domain') \
                .execute()
            
            logger.info(f"✅ Upserted credibility record for {data['domain']}")
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"❌ Failed to upsert credibility: {e}")
            return None
    
    def update_credibility_from_mbfc(self, domain: str, mbfc_data: Dict) -> Optional[Dict]:
        """
        Update a credibility record with MBFC data
        Maps MBFCResult fields to database columns
        
        Args:
            domain: The publication domain
            mbfc_data: Dictionary from MBFCResult model
            
        Returns:
            Updated record or None
        """
        if not self.enabled:
            return None
        
        # Map MBFC fields to database columns
        db_data = {
            'domain': domain.lower(),
            'mbfc_bias_rating': mbfc_data.get('bias_rating'),
            'mbfc_bias_score': mbfc_data.get('bias_score'),
            'mbfc_factual_reporting': mbfc_data.get('factual_reporting'),
            'mbfc_factual_score': mbfc_data.get('factual_score'),
            'mbfc_credibility_rating': mbfc_data.get('credibility_rating'),
            'mbfc_country_freedom_rating': mbfc_data.get('country_freedom_rating'),
            'mbfc_url': mbfc_data.get('mbfc_url'),
            'mbfc_special_tags': mbfc_data.get('special_tags', []),
            'country': mbfc_data.get('country'),
            'media_type': mbfc_data.get('media_type'),
            'ownership': mbfc_data.get('ownership'),
            'funding': mbfc_data.get('funding'),
            'traffic_popularity': mbfc_data.get('traffic_popularity'),
            'failed_fact_checks': mbfc_data.get('failed_fact_checks', []),
            'mbfc_summary': mbfc_data.get('summary'),
            'source': 'mbfc',
            'last_verified_at': datetime.utcnow().isoformat(),
            'is_verified': True
        }
        
        # Remove None values to avoid overwriting with nulls
        db_data = {k: v for k, v in db_data.items() if v is not None}
        
        return self.upsert_credibility(db_data)
    
    def get_publications_by_tier(self, tier: int) -> List[Dict]:
        """
        Get all publications with a specific tier
        
        Args:
            tier: Tier number (1-5)
            
        Returns:
            List of publications
        """
        if not self.enabled:
            return []
        
        try:
            result = self.client.table('media_credibility') \
                .select('*') \
                .eq('assigned_tier', tier) \
                .execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting publications by tier: {e}")
            return []
    
    def get_all_credibility_records(self, limit: int = 100) -> List[Dict]:
        """Get all media credibility records"""
        if not self.enabled:
            return []
        
        try:
            result = self.client.table('media_credibility') \
                .select('*') \
                .limit(limit) \
                .order('domain') \
                .execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting all records: {e}")
            return []

    # ==========================================
    # PROPAGANDA CHANNELS TABLE OPERATIONS
    # ==========================================
    
    def get_propaganda_channel(self, domain: str) -> Optional[Dict]:
        """Look up a propaganda channel by domain"""
        if not self.enabled:
            return None
        
        try:
            result = self.client.table('propaganda_channels') \
                .select('*') \
                .eq('domain', domain.lower()) \
                .single() \
                .execute()
            
            return result.data
        except Exception:
            return None
    
    def upsert_propaganda_channel(self, data: Dict) -> Optional[Dict]:
        """Insert or update a propaganda channel record"""
        if not self.enabled:
            return None
        
        if 'domain' not in data:
            logger.error("❌ Domain is required")
            return None
        
        data['domain'] = data['domain'].lower()
        data['updated_at'] = datetime.utcnow().isoformat()
        
        try:
            result = self.client.table('propaganda_channels') \
                .upsert(data, on_conflict='domain') \
                .execute()
            
            logger.info(f"✅ Upserted propaganda channel: {data['domain']}")
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"❌ Failed to upsert propaganda channel: {e}")
            return None
    
    def get_propaganda_by_country(self, country: str) -> List[Dict]:
        """Get all propaganda channels associated with a country"""
        if not self.enabled:
            return []
        
        try:
            result = self.client.table('propaganda_channels') \
                .select('*') \
                .eq('country_association', country) \
                .execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"Error getting propaganda by country: {e}")
            return []

    # ==========================================
    # AI-POWERED FUNCTIONS
    # ==========================================
    
    async def generate_publication_names(self, domain: str, publication_name: str) -> List[str]:
        """
        AI-powered: Generate alternative names for a publication
        
        Args:
            domain: The publication domain
            publication_name: The primary publication name
            
        Returns:
            List of alternative names/abbreviations
        """
        if not self.ai_enabled:
            logger.warning("AI not enabled - returning default names")
            return [publication_name]
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a media expert. Given a publication domain and name, 
generate all common alternative names, abbreviations, and variations people might use to refer to this publication.

Include:
- Official name
- Common abbreviations (e.g., "NYT" for New York Times)
- Informal names
- Domain variations (without .com, etc.)
- How it's commonly referenced in citations

Return ONLY a JSON object with a "names" array."""),
            ("user", """Publication domain: {domain}
Publication name: {publication_name}

Return JSON: {{"names": ["name1", "name2", ...]}}""")
        ])
        
        try:
            chain = prompt | self.llm
            result = await chain.ainvoke({
                "domain": domain,
                "publication_name": publication_name
            })
            
            parsed = json.loads(result.content)
            names = parsed.get('names', [publication_name])
            
            logger.info(f"✅ Generated {len(names)} names for {domain}")
            return names
            
        except Exception as e:
            logger.error(f"❌ Failed to generate names: {e}")
            return [publication_name]
    
    async def assign_credibility_tier(
        self, 
        mbfc_data: Dict,
        domain: str
    ) -> Dict[str, Any]:
        """
        AI-powered: Assign a credibility tier (1-5) based on MBFC ratings
        
        Tier Guidelines:
        - Tier 1: Official sources, highly credible news (HIGH factual + HIGH credibility)
        - Tier 2: Reputable mainstream media (MOSTLY FACTUAL + MEDIUM-HIGH credibility)
        - Tier 3: Mixed reliability, requires additional verification
        - Tier 4: Low credibility, biased sources
        - Tier 5: Unreliable, propaganda, conspiracy sources
        
        Args:
            mbfc_data: Dictionary with MBFC ratings
            domain: The publication domain
            
        Returns:
            Dictionary with 'tier' (int) and 'reasoning' (str)
        """
        if not self.ai_enabled:
            # Fallback: Simple rule-based tier assignment
            return self._rule_based_tier_assignment(mbfc_data)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a media credibility expert. Analyze the MBFC (Media Bias/Fact Check) ratings and assign a credibility tier from 1-5.

TIER DEFINITIONS:
- Tier 1 (HIGHEST): Official sources, government sites, highly reputable news with HIGH factual reporting and HIGH credibility. Examples: AP, Reuters, official .gov sites.
- Tier 2 (HIGH): Reputable mainstream media with MOSTLY FACTUAL to HIGH reporting and MEDIUM to HIGH credibility. May have moderate bias but factually reliable.
- Tier 3 (MEDIUM): Mixed reliability. May have bias issues or MIXED factual reporting. Requires cross-verification.
- Tier 4 (LOW): Low credibility sources. LOW factual reporting, extreme bias, or history of misinformation.
- Tier 5 (UNRELIABLE): Propaganda, conspiracy sites, VERY LOW factual reporting, known for disinformation. QUESTIONABLE SOURCE tags.

SPECIAL CONSIDERATIONS:
- QUESTIONABLE SOURCE tag → Tier 4-5
- CONSPIRACY-PSEUDOSCIENCE tag → Tier 5
- SATIRE sources → Tier 3-4 (not actual news)
- PRO-SCIENCE tag → Boost reliability
- State-affiliated media → Consider carefully, often Tier 4-5

Return ONLY a JSON object."""),
            ("user", """Analyze this publication and assign a tier:

Domain: {domain}

MBFC Data:
- Bias Rating: {bias_rating}
- Bias Score: {bias_score}
- Factual Reporting: {factual_reporting}
- Factual Score: {factual_score}
- Credibility Rating: {credibility_rating}
- Country: {country}
- Special Tags: {special_tags}
- Failed Fact Checks: {failed_fact_checks}
- Summary: {summary}

Return JSON: {{"tier": 1-5, "reasoning": "explanation"}}""")
        ])
        
        try:
            chain = prompt | self.llm
            result = await chain.ainvoke({
                "domain": domain,
                "bias_rating": mbfc_data.get('bias_rating', 'Unknown'),
                "bias_score": mbfc_data.get('bias_score', 'Unknown'),
                "factual_reporting": mbfc_data.get('factual_reporting', 'Unknown'),
                "factual_score": mbfc_data.get('factual_score', 'Unknown'),
                "credibility_rating": mbfc_data.get('credibility_rating', 'Unknown'),
                "country": mbfc_data.get('country', 'Unknown'),
                "special_tags": mbfc_data.get('special_tags', []),
                "failed_fact_checks": len(mbfc_data.get('failed_fact_checks', [])),
                "summary": mbfc_data.get('summary', 'No summary available')
            })
            
            parsed = json.loads(result.content)
            tier = parsed.get('tier', 3)
            reasoning = parsed.get('reasoning', 'AI-assigned based on MBFC data')
            
            logger.info(f"✅ Assigned Tier {tier} to {domain}")
            return {"tier": tier, "reasoning": reasoning}
            
        except Exception as e:
            logger.error(f"❌ Failed to assign tier: {e}")
            return self._rule_based_tier_assignment(mbfc_data)
    
    def _rule_based_tier_assignment(self, mbfc_data: Dict) -> Dict[str, Any]:
        """
        Fallback rule-based tier assignment when AI is unavailable
        """
        factual = (mbfc_data.get('factual_reporting') or '').upper()
        credibility = (mbfc_data.get('credibility_rating') or '').upper()
        special_tags = [t.upper() for t in mbfc_data.get('special_tags', [])]
        
        # Check for red flags first
        if 'QUESTIONABLE SOURCE' in special_tags or 'CONSPIRACY-PSEUDOSCIENCE' in special_tags:
            return {"tier": 5, "reasoning": "Flagged as questionable or conspiracy source"}
        
        if factual == 'VERY LOW' or credibility == 'LOW CREDIBILITY':
            return {"tier": 5, "reasoning": "Very low factual reporting or low credibility"}
        
        if factual == 'LOW':
            return {"tier": 4, "reasoning": "Low factual reporting"}
        
        if factual == 'HIGH' and credibility in ['HIGH CREDIBILITY', 'MEDIUM CREDIBILITY']:
            return {"tier": 1, "reasoning": "High factual reporting with good credibility"}
        
        if factual in ['MOSTLY FACTUAL', 'HIGH']:
            return {"tier": 2, "reasoning": "Mostly factual reporting"}
        
        if factual == 'MIXED':
            return {"tier": 3, "reasoning": "Mixed factual reporting - requires verification"}
        
        # Default
        return {"tier": 3, "reasoning": "Unable to determine - defaulting to medium tier"}

    async def update_with_ai_features(self, domain: str, mbfc_data: Dict) -> Optional[Dict]:
        """
        Complete update: Store MBFC data and add AI-generated names and tier
        
        Args:
            domain: Publication domain
            mbfc_data: Dictionary from MBFCResult
            
        Returns:
            Updated database record
        """
        if not self.enabled:
            logger.warning("Supabase not enabled")
            return None
        
        # First, update with MBFC data
        record = self.update_credibility_from_mbfc(domain, mbfc_data)
        if not record:
            logger.error(f"Failed to update MBFC data for {domain}")
            return None
        
        # Generate names if AI is available
        publication_name = mbfc_data.get('publication_name', domain)
        names = await self.generate_publication_names(domain, publication_name)
        
        # Assign tier
        tier_result = await self.assign_credibility_tier(mbfc_data, domain)
        
        # Update record with AI features
        ai_updates = {
            'domain': domain.lower(),
            'names': names,
            'assigned_tier': tier_result['tier'],
            'tier_reasoning': tier_result['reasoning']
        }
        
        return self.upsert_credibility(ai_updates)

    # ==========================================
    # UTILITY FUNCTIONS
    # ==========================================
    
    def is_known_domain(self, domain: str) -> bool:
        """Quick check if a domain exists in our database"""
        if not self.enabled:
            return False
        
        record = self.get_credibility_by_domain(domain)
        return record is not None
    
    def is_propaganda_source(self, domain: str) -> bool:
        """Quick check if a domain is flagged as propaganda"""
        if not self.enabled:
            return False
        
        record = self.get_propaganda_channel(domain)
        return record is not None
    
    def get_quick_credibility(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Get a quick credibility summary for a domain
        
        Returns:
            Dictionary with tier, credibility_rating, and is_propaganda
        """
        if not self.enabled:
            return None
        
        # Check propaganda list first
        if self.is_propaganda_source(domain):
            return {
                'domain': domain,
                'tier': 5,
                'credibility_rating': 'LOW CREDIBILITY',
                'is_propaganda': True,
                'source': 'propaganda_channels'
            }
        
        # Check media credibility
        record = self.get_credibility_by_domain(domain)
        if record:
            return {
                'domain': domain,
                'tier': record.get('assigned_tier', 3),
                'credibility_rating': record.get('mbfc_credibility_rating'),
                'is_propaganda': False,
                'source': 'media_credibility'
            }
        
        return None


# Convenience function for quick initialization
def get_supabase_service(config=None) -> SupabaseService:
    """Factory function to get a SupabaseService instance"""
    return SupabaseService(config)


# Test function
if __name__ == "__main__":
    import asyncio
    
    print("🧪 Testing Supabase Service\n")
    
    service = SupabaseService()
    
    if not service.enabled:
        print("❌ Supabase not configured. Set SUPABASE_URL and SUPABASE_KEY")
    else:
        print("✅ Supabase client connected!")
        
        # Test lookup
        result = service.get_credibility_by_domain("cnn.com")
        if result:
            print(f"📰 Found: {result}")
        else:
            print("📭 No record for cnn.com")
        
        # Test AI features if available
        if service.ai_enabled:
            async def test_ai():
                names = await service.generate_publication_names("nytimes.com", "The New York Times")
                print(f"🤖 Generated names: {names}")
                
                tier = await service.assign_credibility_tier({
                    "factual_reporting": "HIGH",
                    "credibility_rating": "HIGH CREDIBILITY",
                    "bias_rating": "LEFT-CENTER"
                }, "nytimes.com")
                print(f"🏷️ Assigned tier: {tier}")
            
            asyncio.run(test_ai())
