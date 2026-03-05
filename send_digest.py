#!/usr/bin/env python3
"""
Weekly email digest sender for ATL Estate Sales.
Reads data/sales.json and sends a formatted HTML email.
Requires SENDGRID_API_KEY, NOTIFY_EMAIL, and FROM_EMAIL env vars.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

DAY_ORDER = ['Thursday', 'Friday', 'Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday']
SOURCE_COLORS = {
    'estatesales.net': '#60a5fa',
    'estatesales.org': '#4ade80',
    'estatesale.com': '#c084fc',
    'gsalr.com': '#fb923c',
    'craigslist': '#a78bfa',
}


def build_html(sales: list[dict]) -> str:
    """Build an HTML email from sales data."""

    # Group by first day
    by_day = {}
    for sale in sales:
        first_day = sale.get('dates', [{}])[0].get('day', 'Unknown')
        by_day.setdefault(first_day, []).append(sale)

    rows = ""
    for day in DAY_ORDER:
        if day not in by_day:
            continue
        rows += f'<tr><td colspan="4" style="background:#1a1d27;color:#6c8cff;font-weight:700;font-size:16px;padding:12px 16px;border-bottom:2px solid #6c8cff;">{day}</td></tr>\n'

        for sale in by_day[day]:
            times = ", ".join(f"{d['day']} {d.get('start','')}–{d.get('end','')}" for d in sale.get('dates', []))
            source_color = SOURCE_COLORS.get(sale.get('source', ''), '#888')
            cats = " ".join(f'<span style="background:#242836;color:#8b8fa3;padding:2px 6px;border-radius:8px;font-size:11px;margin-right:3px">{c}</span>' for c in sale.get('categories', []))

            rows += f'''<tr style="border-bottom:1px solid #2e3346;">
  <td style="padding:10px 16px;vertical-align:top">
    <strong style="color:#e4e6ed">{sale.get('title','')}</strong><br>
    <span style="color:#8b8fa3;font-size:12px">{sale.get('company','')}</span>
  </td>
  <td style="padding:10px 8px;vertical-align:top;color:#e4e6ed;font-size:13px">
    {sale.get('address','')}<br>{sale.get('city','')}, {sale.get('zip','')}
  </td>
  <td style="padding:10px 8px;vertical-align:top;color:#e4e6ed;font-size:13px">{times}</td>
  <td style="padding:10px 8px;vertical-align:top">
    <span style="color:{source_color};font-size:11px;font-weight:600">{sale.get('source','')}</span><br>
    {cats}
  </td>
</tr>\n'''

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:20px;background:#0f1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:800px;margin:0 auto;background:#0f1117;">
    <h1 style="color:#e4e6ed;font-size:22px;margin-bottom:4px;">ATL Estate Sales — This Week</h1>
    <p style="color:#8b8fa3;font-size:13px;margin-bottom:20px;">Generated {datetime.now().strftime('%A, %B %d, %Y')} &bull; {len(sales)} sales found</p>
    <table style="width:100%;border-collapse:collapse;background:#1a1d27;border-radius:10px;overflow:hidden;">
      <thead>
        <tr style="background:#242836;">
          <th style="text-align:left;padding:10px 16px;color:#8b8fa3;font-size:12px;font-weight:600">SALE</th>
          <th style="text-align:left;padding:10px 8px;color:#8b8fa3;font-size:12px;font-weight:600">ADDRESS</th>
          <th style="text-align:left;padding:10px 8px;color:#8b8fa3;font-size:12px;font-weight:600">TIMES</th>
          <th style="text-align:left;padding:10px 8px;color:#8b8fa3;font-size:12px;font-weight:600">SOURCE</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
    <p style="color:#8b8fa3;font-size:12px;margin-top:16px;text-align:center;">
      View the full interactive map at your <a href="https://YOUR_GITHUB_USERNAME.github.io/atlanta-estate-sales/" style="color:#6c8cff">ATL Estate Sales site</a>
    </p>
  </div>
</body>
</html>"""
    return html


def main():
    api_key = os.environ.get('SENDGRID_API_KEY')
    to_email = os.environ.get('NOTIFY_EMAIL')
    from_email = os.environ.get('FROM_EMAIL', 'noreply@example.com')

    if not api_key or not to_email:
        print("Missing SENDGRID_API_KEY or NOTIFY_EMAIL — skipping email")
        sys.exit(0)

    # Load sales data
    data_path = Path(__file__).parent.parent / 'data' / 'sales.json'
    try:
        with open(data_path) as f:
            data = json.load(f)
        sales = data.get('sales', [])
    except Exception as e:
        print(f"Failed to load sales data: {e}")
        sys.exit(1)

    if not sales:
        print("No sales data — skipping email")
        sys.exit(0)

    html = build_html(sales)

    # Send via SendGrid
    import sendgrid
    from sendgrid.helpers.mail import Mail, Email, To, Content

    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    message = Mail(
        from_email=Email(from_email),
        to_emails=To(to_email),
        subject=f"ATL Estate Sales — Week of {datetime.now().strftime('%B %d')}",
        html_content=Content("text/html", html)
    )

    try:
        response = sg.send(message)
        print(f"Email sent! Status: {response.status_code}")
    except Exception as e:
        print(f"Failed to send email: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
