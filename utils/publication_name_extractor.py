# utils/publication_name_extractor.py
"""
Lightweight AI-powered publication name extractor
Extracts clean publication names from page titles using GPT-4o-mini

Future: Will integrate with source credibility database
"""

from typing import Optional, Dict
from urllib.parse import urlparse
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser


class PublicationNameExtractor:
    """Extract clean publication names from page titles using AI"""

    def __init__(self):
        """Initialize with GPT-4o-mini and caching"""
        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0
        ).bind(response_format={"type": "json_object"})

        self.parser = JsonOutputParser()

        # Cache to avoid duplicate API calls
        self.cache: Dict[str, str] = {}

        # Simple prompt for name extraction
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """Extract the clean publication name from a page title.

RULES:
1. Extract ONLY the publication/organization name
2. Remove article titles, dates, navigation, taglines
3. Use proper capitalization
4. Keep it short (2-5 words)

EXAMPLES:
"The Wall Street Journal - Breaking News..." → "The Wall Street Journal"
"CNN - Latest News and Videos" → "CNN"
"Forbes | Business News" → "Forbes"

Return ONLY: {{"name": "Publication Name"}}"""),
            ("user", "Title: {title}\nURL: {url}\n\nReturn JSON only.")
        ])

    async def extract_name(self, url: str, page_title: Optional[str] = None) -> str:
        """
        Extract publication name

        Args:
            url: Source URL
            page_title: Page title (optional, uses URL domain if None)

        Returns:
            Clean publication name
        """
        # Check cache
        cache_key = f"{url}:{page_title}" if page_title else url
        if cache_key in self.cache:
            return self.cache[cache_key]

        # If no title, extract from URL domain
        if not page_title:
            name = self._extract_from_domain(url)
            self.cache[cache_key] = name
            return name

        try:
            # Use AI to extract from title
            chain = self.prompt | self.llm | self.parser
            response = await chain.ainvoke({
                "title": page_title[:500],  # Limit length
                "url": url
            })

            name = response.get('name', self._extract_from_domain(url))
            self.cache[cache_key] = name
            return name

        except Exception as e:
            print(f"⚠️ AI extraction failed for {url}: {e}")
            name = self._extract_from_domain(url)
            self.cache[cache_key] = name
            return name

    def _extract_from_domain(self, url: str) -> str:
        """
        Fallback: Extract name from URL domain

        Args:
            url: Source URL

        Returns:
            Publication name from domain
        """
        try:
            domain = urlparse(url).netloc.lower()
            domain = domain.replace('www.', '')

            # Known major publications (fallback)
            known = {
                'nytimes.com': 'The New York Times',
                'washingtonpost.com': 'The Washington Post',
                'wsj.com': 'The Wall Street Journal',
                'reuters.com': 'Reuters',
                'bbc.com': 'BBC News',
                'bbc.co.uk': 'BBC News',
                'cnn.com': 'CNN',
                'forbes.com': 'Forbes',
                'bloomberg.com': 'Bloomberg',
                'theguardian.com': 'The Guardian',
                'ft.com': 'Financial Times',
            }

            if domain in known:
                return known[domain]

            # Generic: domain to title case
            name = domain.split('.')[0]
            return name.replace('-', ' ').replace('_', ' ').title()

        except:
            return url[:50]


# Singleton instance for reuse
_extractor_instance = None

def get_publication_name_extractor() -> PublicationNameExtractor:
    """Get or create singleton extractor instance"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = PublicationNameExtractor()
    return _extractor_instance