import argparse
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Set
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

EVENT_KEYWORDS = [
    "event", "veranstaltung", "termin", "kalender", "calendar", "agenda", "heute", "monatsansicht"
]

DB_PATH = Path("event_scrape.db")
HTML_DB_PATH = Path("html_event_scrape.db")

def fetch_page(url: str, timeout: int = 10) -> str:
    # gets raw HTML code of page
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


""" Part1 - Web-Crawler for homepage + subpages """

def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    # creates db for saving domains
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            html TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    conn.commit()
    return conn

def store_page(conn: sqlite3.Connection, domain: str, url: str, html: str) -> None:
    # saves page in db or ignores if page already exists
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO pages (domain, url, html, scraped_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (domain, url, html),
        )
        conn.commit()
    except sqlite3.Error as exc:
        print(f"  DB-Fehler bei {url}: {exc}")

def fetch_page(url: str, timeout: int = 10) -> str:
    # gets raw HTML code of page
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def find_event_links(base_url: str, html: str) -> Set[str]:
    # searches for subpages that are possible event pages

    soup = BeautifulSoup(html, "html.parser")
    found: Set[str] = set()

    # checks every link (a) on page
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)

        # checks if links leaves domain (we don't want to leave domain)
        if urlparse(full_url).netloc != urlparse(base_url).netloc:
            continue
        
        haystack = (href + " " + a.get_text(" ", strip=True)).lower()
        # checks if link could be event page by comparing with keywords
        if any(keyword in haystack for keyword in EVENT_KEYWORDS):
            found.add(full_url)

    return found


def crawl_domain(conn: sqlite3.Connection, domain: str, delay: float = 1.0) -> None:
    # crawls over homepage + subpages (if subpages exist) of domain
    base_url = domain if domain.startswith("http") else f"https://{domain}"
    print(f"\n== {base_url} ==")

    # checks if homepage is reachable
    try:
        homepage_html = fetch_page(base_url)
    except requests.RequestException as exc:
        print(f"  Startseite nicht erreichbar, überspringe Domain: {exc}")
        return

    # saves page in db
    #store_page(conn, domain, base_url, homepage_html)
    print(f"  gespeichert: {base_url}")

    # checks for subpages
    event_links = find_event_links(base_url, homepage_html)
    print(f"  {len(event_links)} mögliche Event-Seite(n) gefunden")

    # if links are found -> checks if pages are reachable + saves in db
    for link in event_links:
        time.sleep(delay)  
        try:
            html = fetch_page(link)
        except requests.RequestException as exc:
            print(f"  Fehler bei {link}: {exc}")
            continue
        store_page(conn, domain, link, html)
        print(f"  gespeichert: {link}")


def crawl_domains(domains: Iterable[str], delay: float = 1.0) -> None:
    # iterates over every domain
    conn = init_db()
    for domain in domains:
        crawl_domain(conn, domain.strip(), delay=delay)
    conn.close()

""" Part2 - HTML-Scraper for homepage + subpages """

def init_html_db(db_path: Path = HTML_DB_PATH) -> sqlite3.Connection:
    # creates db for saving domains
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            html TEXT NOT NULL,
            scraped_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new'
        )
        """
    )
    conn.commit()
    return conn

def store_html_code(html_conn:sqlite3.Connection, url:str, html:str):
    try:
        html_conn.execute(
            """
            INSERT OR IGNORE INTO events (url, html, scraped_at)
            VALUES (?, ?, datetime('now'))
            """,
            (url, html),
        )
        html_conn.commit()
    except sqlite3.Error as exc:
        print(f"  DB-Fehler bei {url}: {exc}")

def find_events(base_url: str, html: str):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        full_url = urljoin(base_url, href)

        if urlparse(full_url).netloc != urlparse(base_url).netloc:
            continue
        if full_url == base_url:
            continue
        if "/anmeldung/" in full_url.lower():
            continue

        haystack = (href + " " + a.get_text(" ", strip=True)).lower()
        if any(keyword in haystack for keyword in EVENT_KEYWORDS):
            try:
                html_code = fetch_page(full_url)
            except requests.RequestException as exc:
                print(f"    Fehler bei Detailseite {full_url}: {exc}")
                continue
            results.append((full_url, html_code))

    return results

def get_event_pages(conn: sqlite3.Connection, domain: str):
    try:
        res = conn.execute(
            "SELECT id, url, html FROM pages WHERE domain = ? AND status = 'new'",
            (domain,)
        )
        return res.fetchall()
    except sqlite3.Error as exc:
        print(f"  DB-Fehler beim Lesen der Seiten für {domain}: {exc}")
        return []

def mark_event_page_processed(conn, page_id: int):
    conn.execute("UPDATE pages SET status = 'processed' WHERE id = ?", (page_id,))
    conn.commit()

def get_event_html_code(domain: str, db_path: Path = DB_PATH):
    html_conn = init_html_db()
    conn = sqlite3.connect(db_path)
    overview_pages = get_event_pages(conn, domain)

    found_events = []
    seen_urls: Set[str] = set()

    def add_event(url: str, html: str):
        if url in seen_urls:
            return
        seen_urls.add(url)
        store_html_code(html_conn, url, html)
        found_events.append({"url": url, "domain": domain})

    for page_id, page_url, page_html in overview_pages:
        add_event(page_url, page_html)

        sub_events = find_events(page_url, page_html)
        for event_url, event_html in sub_events:
            add_event(event_url, event_html)

        mark_event_page_processed(conn, page_id)

    conn.close()
    html_conn.close()
    return found_events

def get_stored_html(url: str, db_path: Path = HTML_DB_PATH) -> str | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT html FROM events WHERE url = ?", (url,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()

def main() -> None:
    parser = argparse.ArgumentParser(description="Event-HTML-Crawler")
    parser.add_argument("domains", nargs="+", help="Eine oder mehrere Domains, z.B. magdeburg.de")
    parser.add_argument(
        "--delay", type=float, default=1.0,
        help="Wartezeit zwischen Requests in Sekunden (Standard: 1.0)",
    )
    # takes domains as array
    args = parser.parse_args(["geheimclub.de"])
    # finds homepage + every subpage which is related to events
    crawl_domains(args.domains, delay=args.delay)
    # finds event details pages + stores them in db
    get_event_html_code()


if __name__ == "__main__":
    main()
