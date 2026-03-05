#!/usr/bin/env python3
"""
ATL Estate Sales Scraper — Orchestrator
Runs all source scrapers, deduplicates, geocodes, and outputs data/sales.json
"""

import json
import hashlib
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from sources import estatesales_net, estatesales_org, estatesale_com, gsalr, craigslist

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ── Category keyword mapping ──
CATEGORY_KEYWORDS = {
    'furniture': ['furniture', 'sofa', 'couch', 'table', 'chair', 'dresser', 'desk', 'bed', 'mattress', 'cabinet', 'bookcase', 'armoire', 'hutch', 'nightstand', 'ottoman', 'recliner'],
    'antiques': ['antique', 'vintage', 'victorian', 'depression glass', 'civil war', 'heirloom', 'retro', 'mid-century', 'mcm', 'art deco'],
    'jewelry': ['jewelry', 'jewellery', 'ring', 'necklace', 'bracelet', 'brooch', 'sterling silver', 'gold', 'diamond', 'gemstone', 'costume jewelry', 'watches'],
    'tools': ['tools', 'power tool', 'hand tool', 'craftsman', 'dewalt', 'drill', 'saw', 'wrench', 'woodworking', 'workshop', 'garage'],
    'art': ['painting', 'print', 'sculpture', 'artwork', 'art', 'oil painting', 'watercolor', 'lithograph', 'framed'],
    'collectibles': ['collectible', 'collection', 'coins', 'stamps', 'figurine', 'memorabilia', 'coca-cola', 'neon sign', 'model', 'sports card'],
    'electronics': ['electronics', 'tv', 'stereo', 'computer', 'speaker', 'audio', 'camera', 'vinyl', 'record player', 'turntable'],
    'kitchenware': ['kitchen', 'cookware', 'dishes', 'china', 'crystal', 'silverware', 'flatware', 'appliance', 'pyrex', 'corning', 'le creuset', 'cast iron'],
    'clothing': ['clothing', 'clothes', 'shoes', 'handbag', 'designer', 'purse', 'coat', 'jacket', 'dress', 'suit'],
    'books': ['books', 'book', 'library', 'first edition', 'signed copy', 'novel'],
    'outdoor': ['outdoor', 'patio', 'garden', 'lawn', 'mower', 'grill', 'bbq', 'plant', 'landscaping', 'camping'],
    'sports': ['sports', 'golf', 'tennis', 'bicycle', 'bike', 'fishing', 'exercise', 'treadmill', 'weights', 'kayak'],
    'toys': ['toys', 'toy', 'game', 'puzzle', 'lego', 'doll', 'train set', 'model train', 'action figure']
}


def extract_categories(description: str) -> list[str]:
    """Extract categories from a sale description using keyword matching."""
    if not description:
        return []
    desc_lower = description.lower()
    categories = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in desc_lower for kw in keywords):
            categories.append(category)
    return categories


def generate_id(source: str, url: str, address: str) -> str:
    """Generate a stable ID for a sale based on source + url or address."""
    key = f"{source}:{url or address}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def geocode_address(address: str, city: str, state: str = 'GA') -> tuple[float | None, float | None]:
    """Geocode an address using Nominatim (free, rate-limited)."""
    geolocator = Nominatim(user_agent="atl-estate-sales-finder/1.0")
    query = f"{address}, {city}, {state}"
    try:
        location = geolocator.geocode(query, timeout=10)
        if location:
            return location.latitude, location.longitude
    except (GeocoderTimedOut, GeocoderUnavailable) as e:
        logger.warning(f"Geocoding failed for '{query}': {e}")
    return None, None


def deduplicate_sales(sales: list[dict]) -> list[dict]:
    """Remove duplicate sales based on address + date overlap."""
    seen = {}
    unique = []

    for sale in sales:
        # Normalize address for comparison
        addr_key = (sale.get('address', '').lower().strip(), sale.get('zip', ''))
        dates_key = tuple(sorted(d.get('date', '') for d in sale.get('dates', [])))
        dedup_key = (addr_key, dates_key)

        if dedup_key not in seen:
            seen[dedup_key] = sale
            unique.append(sale)
        else:
            # Keep the one with more info (more photos, longer description)
            existing = seen[dedup_key]
            if len(sale.get('description', '')) > len(existing.get('description', '')):
                unique.remove(existing)
                seen[dedup_key] = sale
                unique.append(sale)

    return unique


def get_day_of_week(date_str: str) -> str:
    """Convert a date string (YYYY-MM-DD) to day of week name."""
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%A')
    except (ValueError, TypeError):
        return ''


def run_scraper(name: str, scrape_func) -> list[dict]:
    """Safely run a scraper and return results."""
    logger.info(f"Running {name} scraper...")
    try:
        results = scrape_func()
        logger.info(f"  {name}: found {len(results)} sales")
        return results
    except Exception as e:
        logger.error(f"  {name} scraper failed: {e}")
        return []


def main():
    logger.info("=== ATL Estate Sales Scraper ===")

    # ── Run all scrapers ──
    all_sales = []

    scrapers = [
        ("EstateSales.NET", estatesales_net.scrape),
        ("EstateSales.org", estatesales_org.scrape),
        ("EstateSale.com", estatesale_com.scrape),
        ("gsalr.com", gsalr.scrape),
        ("Craigslist", craigslist.scrape),
    ]

    for name, func in scrapers:
        results = run_scraper(name, func)
        all_sales.extend(results)

    logger.info(f"Total raw sales: {len(all_sales)}")

    # ── Post-process ──
    # Generate IDs
    for sale in all_sales:
        if not sale.get('id'):
            sale['id'] = generate_id(sale.get('source', ''), sale.get('url', ''), sale.get('address', ''))

    # Extract categories if not already present
    for sale in all_sales:
        if not sale.get('categories'):
            sale['categories'] = extract_categories(sale.get('description', ''))

    # Fill in day-of-week for dates
    for sale in all_sales:
        for d in sale.get('dates', []):
            if not d.get('day') and d.get('date'):
                d['day'] = get_day_of_week(d['date'])

    # Deduplicate
    unique_sales = deduplicate_sales(all_sales)
    logger.info(f"After dedup: {len(unique_sales)} sales")

    # Geocode missing coordinates (with rate limiting)
    geocode_count = 0
    for sale in unique_sales:
        if not sale.get('lat') or not sale.get('lng'):
            if sale.get('address') and sale.get('city'):
                lat, lng = geocode_address(sale['address'], sale['city'])
                if lat and lng:
                    sale['lat'] = lat
                    sale['lng'] = lng
                    geocode_count += 1
                # Nominatim rate limit: 1 request per second
                time.sleep(1.1)
    logger.info(f"Geocoded {geocode_count} addresses")

    # ── Filter to upcoming sales only (today + next 7 days) ──
    today = datetime.now().strftime('%Y-%m-%d')
    week_out = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
    upcoming = []
    for sale in unique_sales:
        sale_dates = [d.get('date', '') for d in sale.get('dates', [])]
        if any(today <= d <= week_out for d in sale_dates):
            upcoming.append(sale)

    logger.info(f"Upcoming (next 7 days): {len(upcoming)} sales")

    # ── Write output ──
    output = {
        "last_updated": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
        "sales": upcoming
    }

    output_path = Path(__file__).parent.parent / 'data' / 'sales.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    logger.info(f"Wrote {len(upcoming)} sales to {output_path}")

    # ── Generate Craigslist feed JSON for the live feed tab ──
    logger.info("Generating Craigslist feed data...")
    try:
        feed_items = craigslist.scrape_feed()
        feed_output = {
            "last_updated": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            "items": feed_items
        }
        feed_path = Path(__file__).parent.parent / 'data' / 'craigslist-feed.json'
        with open(feed_path, 'w') as f:
            json.dump(feed_output, f, indent=2)
        logger.info(f"Wrote {len(feed_items)} feed items to {feed_path}")
    except Exception as e:
        logger.error(f"Feed generation failed: {e}")

    logger.info("=== Done ===")


if __name__ == '__main__':
    main()
