from bs4 import BeautifulSoup
from typing import Dict, List, Any
import re

class HTMLParser:
    """Parse ChatGPT and Perplexity HTML formats"""

    def parse_input(self, html_content: str) -> Dict[str, Any]:
        """
        Extract text and link mappings from pasted HTML
        Returns: {
            'text': str,
            'links': [{'url': str, 'anchor_text': str, 'position': int}],
            'format': 'chatgpt' | 'perplexity'
        }
        """
        soup = BeautifulSoup(html_content, 'html.parser')

        # Detect format
        format_type = self._detect_format(soup)

        if format_type == 'perplexity':
            return self._parse_perplexity(soup)
        else:
            return self._parse_chatgpt(soup)

    def _detect_format(self, soup: BeautifulSoup) -> str:
        """Detect if content is from Perplexity or ChatGPT"""
        text = soup.get_text()
        # Perplexity uses [source+number] style citations
        if re.search(r'\[[\w\s]+\+\d+\]', text):
            return 'perplexity'
        return 'chatgpt'

    def _parse_chatgpt(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parse standard ChatGPT HTML with <a href=""> links"""
        links = []

        # Extract all links
        for idx, link in enumerate(soup.find_all('a', href=True)):
            links.append({
                'url': link['href'],
                'anchor_text': link.get_text().strip(),
                'position': idx
            })

        # Get clean text
        text = soup.get_text(separator=' ', strip=True)

        return {
            'text': text,
            'links': links,
            'format': 'chatgpt'
        }

    def _parse_perplexity(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Parse Perplexity HTML with [source+number] citations"""
        links = []

        # Extract all links first
        link_elements = soup.find_all('a', href=True)

        # Get text and find citation patterns
        text = soup.get_text(separator=' ', strip=True)

        # Find all [source+number] patterns
        citation_pattern = r'\[([\w\s]+)\+(\d+)\]'
        citations = re.finditer(citation_pattern, text)

        # Map citations to links
        for idx, citation in enumerate(citations):
            source_name = citation.group(1)
            source_num = citation.group(2)

            # Try to find matching link
            if idx < len(link_elements):
                links.append({
                    'url': link_elements[idx]['href'],
                    'anchor_text': f"{source_name}+{source_num}",
                    'position': idx
                })

        # If no citations found, fallback to standard link extraction
        if not links:
            for idx, link in enumerate(link_elements):
                links.append({
                    'url': link['href'],
                    'anchor_text': link.get_text().strip(),
                    'position': idx
                })

        return {
            'text': text,
            'links': links,
            'format': 'perplexity'
        }