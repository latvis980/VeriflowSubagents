# agents/publication_bias_detector.py
"""
Publication Bias Detector
Identifies known political leanings and biases of news sources based on metadata
"""

from typing import Dict, Optional, List
from pydantic import BaseModel
from utils.logger import fact_logger


class PublicationProfile(BaseModel):
    """Profile of a publication's known biases"""
    name: str
    political_leaning: str  # "left", "center-left", "center", "center-right", "right"
    bias_rating: float  # 0-10 scale
    ownership: Optional[str] = None
    target_audience: Optional[str] = None
    known_biases: List[str] = []
    credibility_notes: Optional[str] = None


class PublicationBiasDetector:
    """
    Detects publication bias based on metadata and known profiles
    
    This is a simple implementation that can be expanded with a database
    """
    
    def __init__(self):
        # Known publication profiles (can be moved to a database later)
        self.publication_database = {
            # US Publications
            "fox news": PublicationProfile(
                name="Fox News",
                political_leaning="right",
                bias_rating=7.5,
                ownership="Fox Corporation",
                target_audience="Conservative viewers",
                known_biases=["Conservative perspective", "Pro-Republican", "Skeptical of progressive policies"],
                credibility_notes="Mixed factual reporting, often presents conservative viewpoint"
            ),
            "cnn": PublicationProfile(
                name="CNN",
                political_leaning="center-left",
                bias_rating=5.5,
                ownership="Warner Bros. Discovery",
                target_audience="Mainstream liberal-leaning viewers",
                known_biases=["Liberal perspective", "Pro-Democratic at times", "Focus on social issues"],
                credibility_notes="Generally factual with some left-leaning editorial choices"
            ),
            "the new york times": PublicationProfile(
                name="The New York Times",
                political_leaning="center-left",
                bias_rating=4.5,
                ownership="The New York Times Company",
                target_audience="Educated, liberal-leaning readers",
                known_biases=["Liberal editorial stance", "Urban perspective", "Pro-globalization"],
                credibility_notes="High factual accuracy with center-left editorial perspective"
            ),
            "wall street journal": PublicationProfile(
                name="Wall Street Journal",
                political_leaning="center-right",
                bias_rating=4.0,
                ownership="News Corp",
                target_audience="Business professionals, conservatives",
                known_biases=["Conservative editorial page", "Pro-business", "Free market economics"],
                credibility_notes="High factual news reporting with conservative editorial section"
            ),
            "breitbart": PublicationProfile(
                name="Breitbart News",
                political_leaning="right",
                bias_rating=9.0,
                ownership="Breitbart News Network",
                target_audience="Far-right conservatives",
                known_biases=["Far-right perspective", "Nationalist", "Anti-immigration", "Provocative headlines"],
                credibility_notes="Mixed factual reporting with extreme right-wing bias"
            ),
            "the huffington post": PublicationProfile(
                name="The Huffington Post",
                political_leaning="left",
                bias_rating=6.5,
                ownership="BuzzFeed",
                target_audience="Progressive readers",
                known_biases=["Progressive perspective", "Pro-Democratic", "Social justice focus"],
                credibility_notes="Generally factual with strong left-leaning bias"
            ),
            
            # UK Publications
            "the telegraph": PublicationProfile(
                name="The Telegraph",
                political_leaning="center-right",
                bias_rating=5.5,
                ownership="The Telegraph Media Group",
                target_audience="Conservative readers in UK",
                known_biases=["Conservative perspective", "Pro-Brexit", "Traditional values"],
                credibility_notes="Generally reliable with conservative editorial stance"
            ),
            "the guardian": PublicationProfile(
                name="The Guardian",
                political_leaning="center-left",
                bias_rating=5.0,
                ownership="Guardian Media Group",
                target_audience="Progressive readers in UK",
                known_biases=["Liberal-left perspective", "Pro-Labour", "Environmental focus"],
                credibility_notes="High factual accuracy with left-leaning editorial perspective"
            ),
            "daily mail": PublicationProfile(
                name="Daily Mail",
                political_leaning="right",
                bias_rating=7.0,
                ownership="Daily Mail and General Trust",
                target_audience="Middle-class conservatives in UK",
                known_biases=["Right-wing populism", "Sensationalist", "Anti-immigration"],
                credibility_notes="Factually mixed with strong right-wing bias and sensationalism"
            ),
            
            # Neutral/Centrist
            "reuters": PublicationProfile(
                name="Reuters",
                political_leaning="center",
                bias_rating=2.0,
                ownership="Thomson Reuters",
                target_audience="General audience, journalists",
                known_biases=["Minimal bias", "Fact-focused"],
                credibility_notes="Very high factual accuracy, minimal bias"
            ),
            "associated press": PublicationProfile(
                name="Associated Press (AP)",
                political_leaning="center",
                bias_rating=2.0,
                ownership="Cooperative owned by member newspapers",
                target_audience="General audience",
                known_biases=["Minimal bias", "Fact-focused"],
                credibility_notes="Very high factual accuracy, minimal bias"
            ),
            "bbc": PublicationProfile(
                name="BBC",
                political_leaning="center",
                bias_rating=2.5,
                ownership="British Broadcasting Corporation (publicly funded)",
                target_audience="General UK and international audience",
                known_biases=["Minimal bias", "Occasional pro-establishment tendency"],
                credibility_notes="High factual accuracy with efforts toward balance"
            ),
        }
        
        fact_logger.log_component_start(
            "PublicationBiasDetector",
            num_publications=len(self.publication_database)
        )
    
    def detect_publication(self, publication_name: Optional[str]) -> Optional[PublicationProfile]:
        """
        Detect publication bias from name
        
        Args:
            publication_name: Name of the publication (e.g., "The Telegraph")
            
        Returns:
            PublicationProfile if found, None otherwise
        """
        if not publication_name:
            return None
        
        # Normalize the name for matching
        normalized_name = publication_name.lower().strip()
        
        # Try exact match first
        if normalized_name in self.publication_database:
            profile = self.publication_database[normalized_name]
            fact_logger.logger.info(
                f"📰 Detected publication: {profile.name}",
                extra={
                    "publication": profile.name,
                    "political_leaning": profile.political_leaning,
                    "bias_rating": profile.bias_rating
                }
            )
            return profile
        
        # Try partial matching
        for key, profile in self.publication_database.items():
            if key in normalized_name or normalized_name in key:
                fact_logger.logger.info(
                    f"📰 Detected publication (partial match): {profile.name}",
                    extra={
                        "publication": profile.name,
                        "political_leaning": profile.political_leaning,
                        "bias_rating": profile.bias_rating
                    }
                )
                return profile
        
        fact_logger.logger.info(
            f"📰 Unknown publication: {publication_name}",
            extra={"publication": publication_name}
        )
        return None
    
    def get_publication_context(self, publication_name: Optional[str]) -> str:
        """
        Get formatted context about publication bias for use in prompts
        
        Args:
            publication_name: Name of the publication
            
        Returns:
            Formatted string describing publication bias, or empty if unknown
        """
        profile = self.detect_publication(publication_name)
        
        if not profile:
            if publication_name:
                return f"PUBLICATION: {publication_name} (unknown publication - no bias profile available)"
            return "PUBLICATION: Not specified"
        
        context = f"""PUBLICATION: {profile.name}
KNOWN POLITICAL LEANING: {profile.political_leaning}
BIAS RATING: {profile.bias_rating}/10
OWNERSHIP: {profile.ownership or 'Unknown'}
TARGET AUDIENCE: {profile.target_audience or 'Unknown'}
KNOWN BIASES: {', '.join(profile.known_biases)}
CREDIBILITY NOTES: {profile.credibility_notes or 'No notes available'}

⚠️ IMPORTANT: This publication has a known {profile.political_leaning} bias. Consider how this might influence the framing and presentation of information."""
        
        return context
    
    def add_publication(self, profile: PublicationProfile) -> None:
        """
        Add a new publication to the database
        
        Args:
            profile: PublicationProfile to add
        """
        key = profile.name.lower()
        self.publication_database[key] = profile
        fact_logger.logger.info(
            f"➕ Added publication profile: {profile.name}",
            extra={"publication": profile.name}
        )
