# ATL Estate Sales Finder

A free, self-hosted estate sale aggregator for Greater Atlanta. Pulls listings from multiple sources, displays them on an interactive map with day/category filters, and optionally sends a weekly email digest.

## Features

- **Multi-source aggregation**: EstateSales.NET, EstateSales.org, EstateSale.com, gsalr.com, Craigslist
- **Interactive map**: Leaflet.js map with color-coded markers by day
- **Day-of-week tabs**: Filter by Thursday, Friday, Saturday, Sunday
- **Category filters**: Furniture, jewelry, tools, antiques, electronics, and more
- **Source filters**: Toggle which sites to include
- **Search**: Full-text search across titles, descriptions, and locations
- **Print-friendly**: Clean print layout organized by day with addresses and times
- **Mobile responsive**: Works on phone for on-the-go checking
- **Auto-updating**: GitHub Actions scraper runs daily at 6 AM EST
- **Email digest** (optional): Weekly email with the week's sales

## Quick Setup

### 1. Fork this repo

Click **Fork** on GitHub to create your own copy.

### 2. Enable GitHub Pages

Go to **Settings → Pages → Source** and select **Deploy from a branch** → `main` / `(root)`.

Your site will be live at `https://YOUR_USERNAME.github.io/atlanta-estate-sales/`

### 3. Enable the scraper

Go to **Settings → Actions → General** and make sure Actions are enabled.

The scraper runs automatically every day at 6 AM EST. You can also trigger it manually from the **Actions** tab → **Scrape Estate Sales** → **Run workflow**.

### 4. (Optional) Set up email notifications

To receive a weekly email digest:

1. Sign up for a free [SendGrid](https://sendgrid.com/) account (100 emails/day free)
2. Create an API key in SendGrid
3. In your repo, go to **Settings → Secrets and variables → Actions** and add:
   - `SENDGRID_API_KEY` — your SendGrid API key
   - `NOTIFY_EMAIL` — the email address to send digests to
   - `FROM_EMAIL` — the sender email (must be verified in SendGrid)
4. Update the site URL in `scraper/send_digest.py` (search for `YOUR_GITHUB_USERNAME`)

## Running Locally

```bash
# Install Python dependencies
pip install -r scraper/requirements.txt

# Run the scraper
python scraper/main.py

# Serve the site locally
python -m http.server 8000
# Then open http://localhost:8000
```

## Customizing

### Add/remove cities

Edit the `CITIES` list in each scraper file under `scraper/sources/` to cover different areas.

### Add a new source

1. Create a new file in `scraper/sources/` (e.g., `my_source.py`)
2. Implement a `scrape()` function that returns a list of sale dicts matching the schema in `data/sales.json`
3. Import and add it to the `scrapers` list in `scraper/main.py`

### Adjust scraper schedule

Edit the cron expression in `.github/workflows/scrape.yml`. The current schedule is `0 11 * * *` (6 AM EST / 11 AM UTC).

## Scraper Notes

The scrapers parse HTML from public-facing estate sale listing sites. Since these sites can change their HTML structure at any time, scrapers may need occasional updates. Each source is a separate module so fixes are isolated. If a scraper breaks, the site continues to work with data from the sources that succeed.

## Tech Stack

- **Frontend**: Vanilla HTML/CSS/JS + Leaflet.js (no build step)
- **Scraper**: Python + BeautifulSoup + geopy
- **Hosting**: GitHub Pages (free)
- **Automation**: GitHub Actions (free for public repos)
- **Email**: SendGrid (free tier, optional)
