"""
Scraper for gsalr.com — Greater Atlanta garage/estate sales
"""

import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE = "gsalr.com"
BASE_URL = "https://gsalr.com"

URLS = [
    f"{BASE_URL}/garage-sales-atlanta-ga.html",
    f"{BASE_URL}/garage-sales-marietta-ga.html",
    f"{BASE_URL}/garage-sales-roswell-ga.html",
    f"{BASE_URL}/garage-sales-decatur-ga.html",
    f"{BASE_URL}/garage-sales-alpharetta-ga.html",
    f"{BASE_URL}/garage-sales-kennesaw-ga.html",
    f"{BASE_URL}/garage-sales-smyrna-ga.html",
    f"{BASE_URL}/garage-sales-dunwoody-ga.html",
]

HEADERS = {
    "User-Agent": "ATLEstateSalesFinder/1.0 (personal project)",
    "Accept": "text/html,application/xhtml+xml",
}


def parse_dates(text: str) -> list[dict]:
    """Parse gsalr.com date format."""
    dates = []
    if not text:
        return dates

    # gsalr often lists dates as "January 29 - 31, 2026" or individual dates
    # Also: "Fri Jan 29 8am-3pm, Sat Jan 30 8am-2pm"
    lines = re.split(r'[\n\r]+|;\s*', text.strip())

    for line in lines:
        line = line.strip()
        if not line:
            continue

        entry = {"day": "", "date": "", "start": "", "end": ""}

        # Try "Fri Jan 29 8am-3pm" pattern
        match = re.search(
            r'(\w{3,9})\.?\s+(\w{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})?\s*'
            r'(?:(\d{1,2}(?::\d{2})?\s*(?:am|pm))\s*[-–]\s*(\d{1,2}(?::\d{2})?\s*(?:am|pm)))?',
            line, re.IGNORECASE
        )

        if match:
            month_or_day = match.group(1)
            month_str = match.group(2)
            day_str = match.group(3)
            year_str = match.group(4) or str(datetime.now().year)

            try:
                dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
                entry['date'] = dt.strftime('%Y-%m-%d')
                entry['day'] = dt.strftime('%A')
            except ValueError:
                try:
                    dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
                    entry['date'] = dt.strftime('%Y-%m-%d')
                    entry['day'] = dt.strftime('%A')
                except ValueError:
                    pass

            if match.group(5) and match.group(6):
                entry['start'] = match.group(5).strip().upper()
                entry['end'] = match.group(6).strip().upper()

        if entry.get('date'):
            dates.append(entry)

    return dates


def is_estate_sale(text: str) -> bool:
    """Check if a listing is an estate sale (vs regular garage sale)."""
    if not text:
        return False
    lower = text.lower()
    estate_keywords = ['estate sale', 'estate liquidation', 'whole house', 'entire contents',
                       'downsizing', 'moving sale', 'liquidation']
    return any(kw in lower for kw in estate_keywords)


def scrape_page(url: str) -> list[dict]:
    """Scrape a single gsalr.com page, filtering for estate sales."""
    sales = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return sales

    soup = BeautifulSoup(resp.text, 'lxml')

    # gsalr uses various listing formats
    sale_elements = soup.select('.listing, .sale, article, .yard-sale, [class*="listing"]')

    for el in sale_elements:
        try:
            # Get full text to check if it's an estate sale
            full_text = el.get_text()
            if not is_estate_sale(full_text):
                continue

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

            title_el = el.select_one('h2, h3, .title, [class*="title"]')
            if title_el:
                sale['title'] = title_el.get_text(strip=True)
            elif is_estate_sale(full_text):
                # Use first line as title
                first_line = full_text.strip().split('\n')[0].strip()[:100]
                sale['title'] = first_line

            link_el = el.find('a', href=True)
            if link_el:
                href = link_el.get('href', '')
                if href.startswith('/'):
                    href = BASE_URL + href
                sale['url'] = href

            addr_el = el.select_one('.address, [class*="address"]')
            if addr_el:
                sale['address'] = addr_el.get_text(strip=True)

            # Parse city from URL or text
            city_match = re.search(r'garage-sales-([a-z-]+)-ga', url)
            if city_match:
                sale['city'] = city_match.group(1).replace('-', ' ').title()

            zip_match = re.search(r'\b(\d{5})\b', full_text)
            if zip_match:
                sale['zip'] = zip_match.group(1)

            date_el = el.select_one('.dates, [class*="date"]')
            if date_el:
                sale['dates'] = parse_dates(date_el.get_text())

            # Description is usually the main body text
            sale['description'] = full_text.strip()[:500]

            # Coordinates from data attributes
            lat = el.get('data-lat') or el.get('data-latitude')
            lng = el.get('data-lng') or el.get('data-longitude')
            if lat and lng:
                try:
                    sale['lat'] = float(lat)
                    sale['lng'] = float(lng)
                except ValueError:
                    pass

            if sale.get('title') or sale.get('address'):
                sales.append(sale)

        except Exception as e:
            logger.debug(f"Failed to parse gsalr element: {e}")
            continue

    return sales


def scrape() -> list[dict]:
    """Scrape all configured gsalr.com pages."""
    all_sales = []
    for url in URLS:
        page_sales = scrape_page(url)
        all_sales.extend(page_sales)
    return all_sales
