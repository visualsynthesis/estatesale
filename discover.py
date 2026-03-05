#!/usr/bin/env python3
"""
Site Discovery Script — Run this locally to inspect the HTML structure
of each estate sale site. Outputs the info needed to tune the scrapers.

Usage:
    pip install requests beautifulsoup4 lxml
    python scraper/discover.py

This will create a file called 'discovery_report.txt' with the HTML
structure details for each site.
"""

import re
import json
import sys
from collections import Counter

import requests
from bs4 import BeautifulSoup, Tag

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SITES = [
    {
        "name": "EstateSales.NET",
        "url": "https://www.estatesales.net/GA/Atlanta",
        "alt_urls": [
            "https://www.estatesales.net/GA/Marietta",
            "https://www.estatesales.net/GA/Decatur",
        ]
    },
    {
        "name": "EstateSales.org",
        "url": "https://estatesales.org/estate-sales/GA/Atlanta",
        "alt_urls": []
    },
    {
        "name": "EstateSale.com",
        "url": "https://www.estatesale.com/sales/GA/Atlanta/",
        "alt_urls": []
    },
    {
        "name": "gsalr.com",
        "url": "https://gsalr.com/garage-sales-atlanta-ga.html",
        "alt_urls": []
    },
    {
        "name": "Craigslist",
        "url": "https://atlanta.craigslist.org/search/gms?query=estate+sale",
        "alt_urls": []
    },
]


def fetch_page(url: str) -> str | None:
    """Fetch a page and return its HTML."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        print(f"  ✓ Fetched {url} ({len(resp.text)} chars, status {resp.status_code})")
        return resp.text
    except Exception as e:
        print(f"  ✗ Failed to fetch {url}: {e}")
        return None


def find_json_in_scripts(soup: BeautifulSoup) -> list[dict]:
    """Look for JSON data embedded in <script> tags."""
    found = []
    for script in soup.find_all('script'):
        text = script.string or ''
        # Look for JSON arrays or objects that might contain sale data
        json_patterns = re.findall(r'(?:var\s+\w+\s*=\s*|window\.\w+\s*=\s*|JSON\.parse\([\'"]?)(\[?\{.*?\}]?)(?:[\'"]?\))?', text, re.DOTALL)
        for pattern in json_patterns:
            try:
                data = json.loads(pattern)
                if isinstance(data, (list, dict)):
                    # Check if it looks like sale data
                    sample = data[0] if isinstance(data, list) and data else data
                    if isinstance(sample, dict):
                        keys = set(sample.keys())
                        sale_keywords = {'address', 'title', 'date', 'lat', 'lng', 'latitude', 'longitude',
                                         'name', 'location', 'street', 'city', 'zip', 'postal', 'price',
                                         'description', 'url', 'href', 'link', 'id', 'sale'}
                        overlap = keys & sale_keywords
                        if overlap:
                            found.append({
                                'type': 'embedded_json',
                                'keys': list(keys),
                                'overlap_with_sale_keywords': list(overlap),
                                'count': len(data) if isinstance(data, list) else 1,
                                'sample': sample
                            })
            except (json.JSONDecodeError, IndexError, TypeError):
                continue

        # Also look for __NEXT_DATA__ (Next.js) or similar SSR data
        if '__NEXT_DATA__' in text or 'window.__data' in text or 'window.__INITIAL' in text:
            found.append({
                'type': 'ssr_data',
                'note': 'Found server-side rendered data blob',
                'preview': text[:500]
            })

    return found


def analyze_repeating_structures(soup: BeautifulSoup) -> list[dict]:
    """Find repeating HTML structures that likely represent listings."""
    candidates = []

    # Look for common listing container patterns
    for tag_name in ['div', 'article', 'li', 'section', 'a']:
        elements = soup.find_all(tag_name)
        # Group by class
        class_counter = Counter()
        for el in elements:
            if el.get('class'):
                cls = ' '.join(el['class'])
                class_counter[cls] += 1

        # Repeating elements (3+ instances) are likely listings
        for cls, count in class_counter.most_common(20):
            if count >= 3:
                # Get a sample element
                sample = soup.find(tag_name, class_=cls.split())
                if sample:
                    # Check if it contains address-like or listing-like content
                    text = sample.get_text(strip=True)
                    has_address = bool(re.search(r'\d+\s+\w+\s+(St|Ave|Rd|Dr|Blvd|Ln|Way|Ct|Pl)', text))
                    has_date = bool(re.search(r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{1,2}/\d{1,2})', text, re.I))

                    # Get child structure
                    children = []
                    for child in sample.children:
                        if isinstance(child, Tag):
                            child_cls = ' '.join(child.get('class', []))
                            children.append(f"<{child.name} class=\"{child_cls}\">")

                    if has_address or has_date or len(text) > 50:
                        candidates.append({
                            'selector': f"{tag_name}.{'.'.join(cls.split())}",
                            'count': count,
                            'has_address': has_address,
                            'has_date': has_date,
                            'text_preview': text[:200],
                            'child_structure': children[:10],
                            'sample_html': str(sample)[:1000]
                        })

    # Sort: prefer those with addresses and dates
    candidates.sort(key=lambda c: (c['has_address'], c['has_date'], c['count']), reverse=True)
    return candidates[:10]


def find_data_attributes(soup: BeautifulSoup) -> list[dict]:
    """Find elements with data-* attributes that might contain sale info."""
    found = []
    for el in soup.find_all(True):
        data_attrs = {k: v for k, v in el.attrs.items() if k.startswith('data-')}
        if data_attrs:
            interesting = {'data-lat', 'data-lng', 'data-latitude', 'data-longitude',
                          'data-sale-id', 'data-id', 'data-address', 'data-location',
                          'data-price', 'data-date', 'data-url'}
            if set(data_attrs.keys()) & interesting:
                found.append({
                    'tag': el.name,
                    'class': ' '.join(el.get('class', [])),
                    'data_attrs': data_attrs,
                    'text_preview': el.get_text(strip=True)[:100]
                })

    return found[:20]


def find_links_to_detail_pages(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Find links that likely lead to individual sale detail pages."""
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Look for links with patterns like /sale/123, /GA/City/12345, etc.
        if re.search(r'/\d{4,}|/sale/|/listing/|/estate-sale', href, re.I):
            full_url = href if href.startswith('http') else base_url.rstrip('/') + '/' + href.lstrip('/')
            links.append(full_url)

    return list(set(links))[:20]


def analyze_site(site: dict, report_file) -> None:
    """Full analysis of one estate sale site."""
    name = site['name']
    url = site['url']

    report_file.write(f"\n{'='*80}\n")
    report_file.write(f"  {name}\n")
    report_file.write(f"  {url}\n")
    report_file.write(f"{'='*80}\n\n")

    html = fetch_page(url)
    if not html:
        report_file.write("FAILED TO FETCH\n\n")
        return

    soup = BeautifulSoup(html, 'lxml')

    # 1. Check for JSON data in scripts
    report_file.write("── JSON Data in <script> Tags ──\n")
    json_data = find_json_in_scripts(soup)
    if json_data:
        for item in json_data:
            report_file.write(json.dumps(item, indent=2, default=str)[:2000] + "\n\n")
    else:
        report_file.write("No embedded JSON sale data found.\n\n")

    # 2. Repeating structures (likely listings)
    report_file.write("── Repeating HTML Structures (Likely Listings) ──\n")
    structures = analyze_repeating_structures(soup)
    if structures:
        for s in structures[:5]:
            report_file.write(f"\nSelector: {s['selector']} (×{s['count']})\n")
            report_file.write(f"Has address pattern: {s['has_address']}\n")
            report_file.write(f"Has date pattern: {s['has_date']}\n")
            report_file.write(f"Children: {s['child_structure']}\n")
            report_file.write(f"Text preview: {s['text_preview']}\n")
            report_file.write(f"Sample HTML:\n{s['sample_html']}\n")
    else:
        report_file.write("No repeating listing structures found.\n")
        report_file.write("(Site may use JavaScript rendering — check JSON data above)\n\n")

    # 3. Data attributes
    report_file.write("\n── Elements with Interesting data-* Attributes ──\n")
    data_attrs = find_data_attributes(soup)
    if data_attrs:
        for item in data_attrs[:10]:
            report_file.write(json.dumps(item, indent=2, default=str) + "\n")
    else:
        report_file.write("No elements with location/sale data attributes found.\n\n")

    # 4. Links to detail pages
    report_file.write("\n── Links to Detail Pages ──\n")
    links = find_links_to_detail_pages(soup, url)
    if links:
        for link in links[:10]:
            report_file.write(f"  {link}\n")
    else:
        report_file.write("No detail page links found.\n\n")

    # 5. Page title and meta
    report_file.write(f"\n── Page Meta ──\n")
    title = soup.title.string if soup.title else 'No title'
    report_file.write(f"Title: {title}\n")
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc:
        report_file.write(f"Meta desc: {meta_desc.get('content', '')}\n")

    # 6. Raw HTML snippet of the main content area
    report_file.write(f"\n── Main Content Area (first 3000 chars) ──\n")
    main = soup.find('main') or soup.find('div', id='content') or soup.find('div', class_=re.compile(r'content|main|results|listings', re.I))
    if main:
        report_file.write(str(main)[:3000] + "\n")
    else:
        body = soup.find('body')
        if body:
            report_file.write(str(body)[:3000] + "\n")

    report_file.write("\n\n")


def main():
    print("╔══════════════════════════════════════════════╗")
    print("║  ATL Estate Sales — Site Discovery Script    ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    report_path = "discovery_report.txt"

    with open(report_path, 'w') as f:
        f.write("ATL Estate Sales — Site Discovery Report\n")
        f.write(f"Generated by discover.py\n")
        f.write("="*80 + "\n")

        for site in SITES:
            print(f"\nAnalyzing {site['name']}...")
            analyze_site(site, f)

    print(f"\n✓ Report written to: {report_path}")
    print(f"  File size: {len(open(report_path).read())} chars")
    print()
    print("NEXT STEPS:")
    print("1. Open discovery_report.txt")
    print("2. Share the contents with Claude so I can update the scrapers")
    print("   with the correct CSS selectors for each site")
    print()


if __name__ == '__main__':
    main()
