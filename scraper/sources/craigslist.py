"""
Scraper for Atlanta Craigslist — Garage & Moving Sales section
Filters for estate sales specifically.
"""

import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE = "craigslist"
BASE_URL = "https://atlanta.craigslist.org"
SEARCH_URL = f"{BASE_URL}/search/gms"

HEADERS = {
    "User-Agent": "ATLEstateSalesFinder/1.0 (personal project)",
    "Accept": "text/html,application/xhtml+xml",
}


def is_estate_sale(title: str, body: str = "") -> bool:
    """Filter for estate sales (vs generic garage sales)."""
    text = (title + " " + body).lower()
    keywords = ['estate sale', 'estate liquidation', 'whole house sale',
                'entire contents', 'downsizing sale']
    return any(kw in text for kw in keywords)


def parse_cl_dates(text: str) -> list[dict]:
    """Parse dates from Craigslist posting text.

    CL posts often have informal date formats like:
    - "Saturday & Sunday 8am-3pm"
    - "Feb 27-28, 9am to 4pm"
    - "This weekend"
    """
    dates = []
    if not text:
        return dates

    lines = re.split(r'[\n\r]+', text)
    for line in lines:
        line = line.strip()

        # "Saturday 8am-3pm" or "Saturday & Sunday 8am-3pm"
        day_pattern = re.findall(
            r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*'
            r'(?:(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*[-–to]+\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)))?',
            line, re.IGNORECASE
        )

        for match in day_pattern:
            entry = {
                "day": match[0].title(),
                "date": "",
                "start": match[1].strip().upper() if match[1] else "",
                "end": match[2].strip().upper() if match[2] else ""
            }
            dates.append(entry)

    return dates


def scrape() -> list[dict]:
    """Scrape Atlanta Craigslist garage/moving sales for estate sales."""
    sales = []

    # Search with estate sale query
    params = {"query": "estate sale", "sort": "date"}

    try:
        resp = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch Craigslist: {e}")
        return sales

    soup = BeautifulSoup(resp.text, 'lxml')

    # CL listing rows
    listings = soup.select('.result-row, .cl-static-search-result, li.result-info, .cl-search-result')

    for el in listings:
        try:
            sale = {
                "source": SOURCE,
                "title": "",
                "company": "",
                "address": "",
                "city": "",
                "zip": "",
                "lat": None,
                "lng": None,
                "dates": [],
                "description": "",
                "categories": [],
                "photos": 0,
                "url": "",
                "id": ""
            }

            # Title
            title_el = el.select_one('.result-title, .posting-title, a.titlestring, .title')
            if title_el:
                sale['title'] = title_el.get_text(strip=True)

            # Only include if it looks like an estate sale
            if not is_estate_sale(sale['title']):
                continue

            # URL
            link_el = el.select_one('a[href]')
            if link_el:
                href = link_el.get('href', '')
                if href.startswith('/'):
                    href = BASE_URL + href
                sale['url'] = href

            # Location/neighborhood
            hood_el = el.select_one('.result-hood, .neighborhood, .supertitle')
            if hood_el:
                hood_text = hood_el.get_text(strip=True).strip('() ')
                sale['city'] = hood_text or 'Atlanta'
            else:
                sale['city'] = 'Atlanta'

            # Date posted
            date_el = el.select_one('time, .result-date, .meta')
            if date_el:
                datetime_attr = date_el.get('datetime', '')
                if datetime_attr:
                    try:
                        dt = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                        # CL posts don't always have sale dates in the listing;
                        # we'll try to parse from description if we fetch the detail page
                    except ValueError:
                        pass

            # Price (sometimes listed)
            price_el = el.select_one('.result-price')
            if price_el:
                sale['description'] = price_el.get_text(strip=True)

            if sale.get('title'):
                sales.append(sale)

        except Exception as e:
            logger.debug(f"Failed to parse CL listing: {e}")
            continue

    # Optionally: fetch detail pages for address/date info
    # (commented out to avoid excessive requests; enable if needed)
    # for sale in sales[:20]:  # limit to avoid hammering CL
    #     if sale.get('url'):
    #         enrich_from_detail(sale)

    return sales


def enrich_from_detail(sale: dict) -> None:
    """Fetch a CL detail page to get address and date info."""
    try:
        resp = requests.get(sale['url'], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        # Body text
        body_el = soup.select_one('#postingbody, .body')
        if body_el:
            body_text = body_el.get_text(strip=True)
            sale['description'] = body_text[:500]

            # Try to extract address
            addr_match = re.search(r'(\d+\s+[\w\s]+(?:St|Ave|Rd|Dr|Blvd|Ln|Way|Ct|Pl|Pkwy|Ter|Cir)\.?(?:\s+\w+)?)', body_text)
            if addr_match:
                sale['address'] = addr_match.group(1).strip()

            # Try to extract zip
            zip_match = re.search(r'\b(3\d{4})\b', body_text)
            if zip_match:
                sale['zip'] = zip_match.group(1)

            # Parse dates from body
            sale['dates'] = parse_cl_dates(body_text)

        # Map coordinates
        map_el = soup.select_one('#map, [data-latitude]')
        if map_el:
            lat = map_el.get('data-latitude')
            lng = map_el.get('data-longitude')
            if lat and lng:
                try:
                    sale['lat'] = float(lat)
                    sale['lng'] = float(lng)
                except ValueError:
                    pass

    except Exception as e:
        logger.debug(f"Failed to fetch CL detail: {e}")
