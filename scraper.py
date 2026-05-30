import requests
import time
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from datetime import timezone

BASE_URL = "https://tenders.bhel.com/tenders"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}
PAGE_DELAY = 1.5  # seconds between requests


@dataclass
class Tender:
    nit_number: str
    notification_number: str
    title: str
    unit: str
    opening_date: str
    detail_url: str
    is_gem: bool = field(init=False)
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self):
        self.is_gem = self.notification_number.startswith("GEM/")


def fetch_page(page: int = 0) -> Optional[BeautifulSoup]:
    params = {"page": page}
    try:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  Error fetching page {page}: {e}")
        return None


def parse_tenders(soup: BeautifulSoup) -> list[Tender]:
    tenders = []
    rows = soup.select("table tbody tr")

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue

        nit_cell = cells[0]
        detail_cell = cells[1]
        unit_cell = cells[2]
        date_cell = cells[3]

        nit_number = nit_cell.get_text(strip=True)

        notification_number = ""
        title = ""
        detail_url = ""

        for strong in detail_cell.find_all("strong"):
            label = strong.get_text(strip=True)
            sibling = strong.next_sibling
            value = sibling.strip() if sibling and isinstance(sibling, str) else ""

            if "Tender Notification Number" in label:
                notification_number = value
            elif "Tender Description" in label:
                link = strong.find_next("a")
                if link:
                    title = link.get_text(strip=True)
                    href = link.get("href", "")
                    detail_url = href if href.startswith("http") else f"https://tenders.bhel.com{href}"

        unit = unit_cell.get_text(strip=True)
        opening_date = date_cell.get_text(strip=True)

        if nit_number and title:
            tenders.append(Tender(
                nit_number=nit_number,
                notification_number=notification_number,
                title=title,
                unit=unit,
                opening_date=opening_date,
                detail_url=detail_url,
            ))

    return tenders


def has_next_page(soup: BeautifulSoup) -> bool:
    next_link = soup.select_one("a[title='Go to next page'], li.next a")
    return next_link is not None


def scrape_all(max_pages: int = 50, known_nit_numbers: set[str] = None) -> list[Tender]:
    """
    Scrapes all pages of tenders.bhel.com.
    Stops early if known_nit_numbers is provided and all tenders on a page are already known
    (avoids re-scraping the full history on every daily run).
    """
    known = known_nit_numbers or set()
    all_tenders = []
    page = 0

    while page < max_pages:
        print(f"  Fetching page {page}...")
        soup = fetch_page(page)
        if not soup:
            break

        tenders = parse_tenders(soup)
        if not tenders:
            print("  No tenders found on page, stopping.")
            break

        new_on_page = [t for t in tenders if t.nit_number not in known]
        all_tenders.extend(new_on_page)

        if known and len(new_on_page) == 0:
            print(f"  All tenders on page {page} already known, stopping early.")
            break

        if not has_next_page(soup):
            print("  No next page, done.")
            break

        page += 1
        time.sleep(PAGE_DELAY)

    return all_tenders


if __name__ == "__main__":
    print("Scraping tenders.bhel.com (first 2 pages for testing)...\n")
    tenders = scrape_all(max_pages=2)

    print(f"\nFound {len(tenders)} tenders total.")
    gem_tenders = [t for t in tenders if t.is_gem]
    print(f"GeM tenders: {len(gem_tenders)}")
    print(f"Non-GeM tenders: {len(tenders) - len(gem_tenders)}")

    print("\n--- Sample (first 5) ---")
    for t in tenders[:5]:
        print(f"  NIT:          {t.nit_number}")
        print(f"  Notification: {t.notification_number}")
        print(f"  Title:        {t.title}")
        print(f"  Unit:         {t.unit}")
        print(f"  Opening:      {t.opening_date}")
        print(f"  GeM:          {t.is_gem}")
        print(f"  URL:          {t.detail_url}")
        print()
