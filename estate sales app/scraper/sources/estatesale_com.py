"""
Scraper for EstateSale.com — Atlanta area
"""

import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE = "estatesale.com"
BASE_URL = "https://www.estatesale.com"

URLS = [
    f"{BASE_URL}/sales/GA/Atlanta/",
    f"{BASE_URL}/sales/GA/Marietta/",
    f"{BASE_URL}/sales/GA/Roswell/",
    f"{BASE_URL}/sales/GA/Decatur/",
    f"{BASE_URL}/sales/GA/Alpharetta/",
    f"{BASE_URL}/sales/GA/Kennesaw/",
]

HEADERS = {
    "User-Agent": "ATLEstateSalesFinder/1.0 (personal project)",
    "Accept": "text/html,application/xhtml+xml",
}


def parse_dates(text: str) -> list[dict]:
    """Parse dates from EstateSale.com format."""
    dates = []
    if not text:
        return dates

    lines = re.split(r'[\n\r]+|,\s*(?=\w{3})', text.strip())
    for line in lines:
        line = line.strip()
        if not line:
            continue

        entry = {"day": "", "date": "", "start": "", "end": ""}

        # Pattern: "Feb 27 (Fri) 10am-5pm" or "Friday, February 27, 2026 10:00 AM - 5:00 PM"
        match = re.search(
            r'(\w+)\.?\s+(\d{1,2}),?\s*(\d{4})?\s*'
            r'(?:\((\w+)\))?\s*'
            r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))\s*[-–to]+\s*'
            r'(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))',
            line
        )

        if match:
            month_str, day_str = match.group(1), match.group(2)
            year_str = match.group(3) or str(datetime.now().year)
            start_time, end_time = match.group(5).strip(), match.group(6).strip()

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

            entry['start'] = start_time.upper()
            entry['end'] = end_time.upper()

        if entry.get('date') or entry.get('day'):
            dates.append(entry)

    return dates


def scrape_page(url: str) -> list[dict]:
    """Scrape a single EstateSale.com page."""
    sales = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return sales

    soup = BeautifulSoup(resp.text, 'lxml')
    sale_elements = soup.select('.sale-listing, .listing, article, .sale-card, [class*="sale"]')

    for el in sale_elements:
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

            title_el = el.select_one('h2, h3, .title, [class*="title"]')
            if title_el:
                sale['title'] = title_el.get_text(strip=True)

            company_el = el.select_one('.company, [class*="company"], [class*="host"]')
            if company_el:
                sale['company'] = company_el.get_text(strip=True)

            link_el = el.select_one('a[href*="/sales/"]') or el.find('a', href=True)
            if link_el:
                href = link_el.get('href', '')
                if href.startswith('/'):
                    href = BASE_URL + href
                sale['url'] = href

            addr_el = el.select_one('.address, [class*="address"]')
            if addr_el:
                sale['address'] = addr_el.get_text(strip=True)

            location_el = el.select_one('.location, [class*="location"], [class*="city"]')
            if location_el:
                loc_text = location_el.get_text(strip=True)
                loc_match = re.search(r'([A-Za-z\s]+),?\s*GA\s*(\d{5})?', loc_text)
                if loc_match:
                    sale['city'] = loc_match.group(1).strip()
                    if loc_match.group(2):
                        sale['zip'] = loc_match.group(2)

            date_el = el.select_one('.dates, [class*="date"]')
            if date_el:
                sale['dates'] = parse_dates(date_el.get_text())

            desc_el = el.select_one('.description, [class*="desc"], p')
            if desc_el:
                sale['description'] = desc_el.get_text(strip=True)[:500]

            if sale.get('title') or sale.get('address'):
                sales.append(sale)

        except Exception as e:
            logger.debug(f"Failed to parse element: {e}")
            continue

    return sales


def scrape() -> list[dict]:
    """Scrape all configured EstateSale.com pages."""
    all_sales = []
    for url in URLS:
        page_sales = scrape_page(url)
        all_sales.extend(page_sales)
    return all_sales
