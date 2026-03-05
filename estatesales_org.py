"""
Scraper for EstateSales.org — Atlanta area
Scrapes: estatesales.org/estate-sales/ga/atlanta and nearby
"""

import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE = "estatesales.org"
BASE_URL = "https://estatesales.org"

# Pages to scrape
URLS = [
    f"{BASE_URL}/estate-sales/ga/atlanta",
    f"{BASE_URL}/estate-sales/ga/marietta",
    f"{BASE_URL}/estate-sales/ga/roswell",
    f"{BASE_URL}/estate-sales/ga/decatur",
    f"{BASE_URL}/estate-sales/ga/alpharetta",
    f"{BASE_URL}/estate-sales/ga/kennesaw",
    f"{BASE_URL}/estate-sales/ga/smyrna",
    f"{BASE_URL}/estate-sales/ga/dunwoody",
    f"{BASE_URL}/estate-sales/ga/sandy-springs",
    f"{BASE_URL}/estate-sales/ga/tucker",
]

HEADERS = {
    "User-Agent": "ATLEstateSalesFinder/1.0 (personal project)",
    "Accept": "text/html,application/xhtml+xml",
}


def parse_dates(text: str) -> list[dict]:
    """Parse date information from EstateSales.org listing text."""
    dates = []
    if not text:
        return dates

    lines = re.split(r'[\n\r]+', text.strip())
    for line in lines:
        line = line.strip()
        if not line:
            continue

        entry = {"day": "", "date": "", "start": "", "end": ""}

        # Look for patterns like "Fri, Feb 27 8:00am - 3:00pm"
        match = re.search(
            r'(\w{3,9})\.?,?\s*(\w{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})?\s*'
            r'(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))\s*[-–to]+\s*'
            r'(\d{1,2}:\d{2}\s*(?:am|pm|AM|PM))',
            line
        )

        if match:
            day_raw, month_str, day_str = match.group(1), match.group(2), match.group(3)
            year_str = match.group(4) or str(datetime.now().year)
            start_time, end_time = match.group(5).strip(), match.group(6).strip()

            # Parse date
            try:
                dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
                entry['date'] = dt.strftime('%Y-%m-%d')
                entry['day'] = dt.strftime('%A')
            except ValueError:
                pass

            entry['start'] = start_time.upper().replace('AM', ' AM').replace('PM', ' PM').strip()
            entry['end'] = end_time.upper().replace('AM', ' AM').replace('PM', ' PM').strip()

        if entry.get('date') or entry.get('day'):
            dates.append(entry)

    return dates


def scrape_page(url: str) -> list[dict]:
    """Scrape a single EstateSales.org listing page."""
    sales = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return sales

    soup = BeautifulSoup(resp.text, 'lxml')

    # EstateSales.org uses various listing containers
    sale_elements = soup.select('.sale-listing, .sale-card, .listing-item, article')

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

            # Title
            title_el = el.select_one('h2, h3, .sale-title, [class*="title"]')
            if title_el:
                sale['title'] = title_el.get_text(strip=True)

            # Company
            company_el = el.select_one('.company, .hosted-by, [class*="company"]')
            if company_el:
                sale['company'] = company_el.get_text(strip=True).replace('Hosted by', '').replace('by', '').strip()

            # Link
            link_el = el.select_one('a[href*="/estate-sales/"]') or el.find('a', href=True)
            if link_el:
                href = link_el.get('href', '')
                if href.startswith('/'):
                    href = BASE_URL + href
                sale['url'] = href

            # Address
            addr_el = el.select_one('.address, [class*="address"], [itemprop="streetAddress"]')
            if addr_el:
                full_addr = addr_el.get_text(strip=True)
                sale['address'] = full_addr

            # City & Zip
            location_el = el.select_one('.location, .city-state, [class*="location"]')
            if location_el:
                loc_text = location_el.get_text(strip=True)
                # Try "City, GA 30309" pattern
                loc_match = re.search(r'([A-Za-z\s]+),\s*GA\s*(\d{5})?', loc_text)
                if loc_match:
                    sale['city'] = loc_match.group(1).strip()
                    if loc_match.group(2):
                        sale['zip'] = loc_match.group(2)

            # Dates
            date_el = el.select_one('.dates, .sale-dates, [class*="date"]')
            if date_el:
                sale['dates'] = parse_dates(date_el.get_text())

            # Description
            desc_el = el.select_one('.description, .sale-description, p, [class*="desc"]')
            if desc_el:
                sale['description'] = desc_el.get_text(strip=True)[:500]

            # Photos
            photo_el = el.select_one('.photo-count, [class*="photo"]')
            if photo_el:
                count_match = re.search(r'(\d+)', photo_el.get_text())
                if count_match:
                    sale['photos'] = int(count_match.group(1))

            if sale.get('title') or sale.get('address'):
                sales.append(sale)

        except Exception as e:
            logger.debug(f"Failed to parse element: {e}")
            continue

    return sales


def scrape() -> list[dict]:
    """Scrape all configured EstateSales.org pages."""
    all_sales = []
    for url in URLS:
        page_sales = scrape_page(url)
        all_sales.extend(page_sales)
    return all_sales
