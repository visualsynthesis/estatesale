"""
Scraper for EstateSales.NET — Greater Atlanta area
Scrapes: estatesales.net/GA/{city} for multiple Atlanta-metro cities
"""

import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

SOURCE = "estatesales.net"
BASE_URL = "https://www.estatesales.net"

# Greater Atlanta metro cities to scrape
CITIES = [
    "Atlanta", "Decatur", "Marietta", "Roswell", "Alpharetta",
    "Sandy-Springs", "Kennesaw", "Smyrna", "Tucker", "Dunwoody",
    "Lawrenceville", "Duluth", "Johns-Creek", "Peachtree-City",
    "Brookhaven", "Chamblee", "Doraville", "Stone-Mountain",
    "Lithonia", "Conyers", "Douglasville", "Woodstock",
    "Canton", "Cumming", "Snellville", "Norcross"
]

HEADERS = {
    "User-Agent": "ATLEstateSalesFinder/1.0 (personal project; atlanta estate sale aggregator)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def parse_date_range(date_text: str) -> list[dict]:
    """Parse date/time text from EstateSales.NET into structured date objects.

    Expected formats like:
    - "Thu. Feb 27, 2026 9:00 AM to 4:00 PM"
    - "Fri. Feb 28 9am-3pm"
    Various formats are handled with fallbacks.
    """
    dates = []
    if not date_text:
        return dates

    # Split on newlines or <br> for multiple days
    lines = re.split(r'[\n\r]+|<br\s*/?>|\|', date_text.strip())

    for line in lines:
        line = line.strip()
        if not line:
            continue

        entry = {"day": "", "date": "", "start": "", "end": ""}

        # Try to extract day name
        day_match = re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|Mon|Tue|Wed|Thu|Fri|Sat|Sun)', line, re.IGNORECASE)
        if day_match:
            day_abbrevs = {'mon': 'Monday', 'tue': 'Tuesday', 'wed': 'Wednesday', 'thu': 'Thursday', 'fri': 'Friday', 'sat': 'Saturday', 'sun': 'Sunday'}
            raw = day_match.group(1)
            entry['day'] = day_abbrevs.get(raw[:3].lower(), raw.title())

        # Try to extract date (Feb 27, 2026 or similar)
        date_match = re.search(r'(\w{3,9})\.?\s+(\d{1,2}),?\s*(\d{4})?', line)
        if date_match:
            month_str, day_str = date_match.group(1), date_match.group(2)
            year_str = date_match.group(3) or str(datetime.now().year)
            try:
                dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
                entry['date'] = dt.strftime('%Y-%m-%d')
                if not entry['day']:
                    entry['day'] = dt.strftime('%A')
            except ValueError:
                try:
                    dt = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
                    entry['date'] = dt.strftime('%Y-%m-%d')
                    if not entry['day']:
                        entry['day'] = dt.strftime('%A')
                except ValueError:
                    pass

        # Try to extract times
        time_match = re.search(r'(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))\s*(?:to|-|–)\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))', line, re.IGNORECASE)
        if time_match:
            entry['start'] = time_match.group(1).strip().upper()
            entry['end'] = time_match.group(2).strip().upper()
            # Normalize: "9AM" -> "9:00 AM"
            for key in ('start', 'end'):
                val = entry[key]
                if re.match(r'^\d{1,2}(AM|PM)$', val):
                    val = val[:-2] + ':00 ' + val[-2:]
                entry[key] = val

        if entry['date'] or entry['day']:
            dates.append(entry)

    return dates


def scrape_city(city: str) -> list[dict]:
    """Scrape estate sales for a single city."""
    url = f"{BASE_URL}/GA/{city}"
    sales = []

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return sales

    soup = BeautifulSoup(resp.text, 'lxml')

    # EstateSales.NET uses various class names for sale listings
    # Common patterns: .es-sale, .sale-item, article with sale data
    sale_elements = soup.select('.es-sale, .sale-item, [data-sale-id], .resultsBody .row')

    if not sale_elements:
        # Fallback: try to find any container with sale-like content
        sale_elements = soup.find_all('div', class_=re.compile(r'sale|listing|result', re.I))

    for el in sale_elements:
        try:
            sale = parse_sale_element(el, city)
            if sale and sale.get('address'):
                sales.append(sale)
        except Exception as e:
            logger.debug(f"Failed to parse sale element: {e}")
            continue

    return sales


def parse_sale_element(el, city: str) -> dict | None:
    """Parse a single sale listing element."""
    sale = {
        "source": SOURCE,
        "title": "",
        "company": "",
        "address": "",
        "city": city.replace("-", " "),
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
    title_el = el.select_one('h3, h2, .sale-title, .es-sale-title, [class*="title"]')
    if title_el:
        sale['title'] = title_el.get_text(strip=True)

    # Company
    company_el = el.select_one('.company-name, .es-company, [class*="company"]')
    if company_el:
        sale['company'] = company_el.get_text(strip=True)

    # URL
    link_el = el.select_one('a[href*="/GA/"]') or el.find('a', href=True)
    if link_el:
        href = link_el.get('href', '')
        if href.startswith('/'):
            href = BASE_URL + href
        sale['url'] = href

    # Address
    addr_el = el.select_one('.sale-address, .address, [class*="address"], [itemprop="streetAddress"]')
    if addr_el:
        sale['address'] = addr_el.get_text(strip=True)

    # Zip code
    zip_el = el.select_one('[itemprop="postalCode"], .zip, [class*="zip"]')
    if zip_el:
        sale['zip'] = zip_el.get_text(strip=True)
    else:
        # Try to extract from address or URL
        zip_match = re.search(r'\b(\d{5})\b', sale.get('url', '') + ' ' + sale.get('address', ''))
        if zip_match:
            sale['zip'] = zip_match.group(1)

    # City (might be different from the URL city)
    city_el = el.select_one('[itemprop="addressLocality"], .city, [class*="city"]')
    if city_el:
        sale['city'] = city_el.get_text(strip=True)

    # Dates
    date_el = el.select_one('.sale-dates, .dates, [class*="date"]')
    if date_el:
        sale['dates'] = parse_date_range(date_el.get_text())

    # Description
    desc_el = el.select_one('.sale-description, .description, [class*="desc"], p')
    if desc_el:
        sale['description'] = desc_el.get_text(strip=True)[:500]

    # Photos count
    photo_el = el.select_one('.photo-count, [class*="photo"], [class*="image"]')
    if photo_el:
        count_match = re.search(r'(\d+)', photo_el.get_text())
        if count_match:
            sale['photos'] = int(count_match.group(1))

    # Coordinates (sometimes embedded in data attributes)
    lat = el.get('data-lat') or el.get('data-latitude')
    lng = el.get('data-lng') or el.get('data-longitude')
    if lat and lng:
        try:
            sale['lat'] = float(lat)
            sale['lng'] = float(lng)
        except ValueError:
            pass

    return sale if sale.get('title') or sale.get('address') else None


def scrape() -> list[dict]:
    """Scrape all Greater Atlanta cities from EstateSales.NET."""
    all_sales = []

    for city in CITIES:
        city_sales = scrape_city(city)
        all_sales.extend(city_sales)
        logger.info(f"  EstateSales.NET/{city}: {len(city_sales)} sales")

    return all_sales
