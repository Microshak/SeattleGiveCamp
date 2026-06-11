import time
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

SKIP_EXTENSIONS = frozenset({
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".mp4", ".mp3", ".avi", ".mov", ".wmv",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".iso", ".bin", ".exe", ".dmg",
})

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


class Crawler:
    def __init__(
        self,
        start_url: str,
        max_pages: int = 50,
        delay: float = 1.0,
        same_domain_only: bool = True,
        verbose: bool = False,
    ):
        self.start_url = start_url
        self.max_pages = max_pages
        self.delay = delay
        self.same_domain_only = same_domain_only
        self.verbose = verbose
        self.start_domain = urlparse(start_url).netloc

        self.visited: set[str] = set()
        self.queue: deque[str] = deque()
        self.count = 0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def _normalize(self, url: str, base: str) -> str | None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https", ""):
            return None
        joined = urljoin(base, url)
        frag_parsed = urlparse(joined)
        clean = f"{frag_parsed.scheme}://{frag_parsed.netloc}{frag_parsed.path}"
        if not clean.rstrip("/"):
            return None
        return clean.rstrip("/")

    def _should_skip(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        for ext in SKIP_EXTENSIONS:
            if path.endswith(ext):
                return True
        return False

    def _is_same_domain(self, url: str) -> bool:
        return urlparse(url).netloc == self.start_domain

    def _extract_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["script", "style", "nav"]):
            tag.decompose()
        body = soup.find("body")
        if body is None:
            body = soup
        text = body.get_text(separator=" ", strip=True)
        return text[:3000]

    def _extract_links(self, html: str, base: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        links: list[str] = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            if href.startswith("mailto:") or href.startswith("#"):
                continue
            normalized = self._normalize(href, base)
            if normalized is None:
                continue
            if self._should_skip(normalized):
                continue
            if self.same_domain_only and not self._is_same_domain(normalized):
                continue
            links.append(normalized)
        return links

    def run(self, analyze_fn, write_email_fn, write_form_fn, write_all_emails_fn=None):
        self.queue.append(self.start_url)

        while self.queue and self.count < self.max_pages:
            url = self.queue.popleft()
            if url in self.visited:
                continue
            self.visited.add(url)

            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
            except requests.exceptions.RequestException as e:
                if self.verbose:
                    print(f"[SKIP] {url} — {e}")
                continue

            self.count += 1
            text = self._extract_text(resp.text)
            result = analyze_fn(url, text)
            result_type = result.get("type", "none")
            result_value = result.get("value", "")
            result_email_type = result.get("email_type", "general")
            all_emails = result.get("all_emails")

            if self.verbose:
                total = self.max_pages
                out = f"[{self.count}/{total}] Crawling: {url}\n  → result: {result_type}"
                if result_type == "email":
                    email_count = len(all_emails) if all_emails else 1
                    out += f" → {result_value} ({result_email_type}) ✓ {email_count} email(s) written"
                    if all_emails and write_all_emails_fn:
                        write_all_emails_fn(url, all_emails)
                    else:
                        write_email_fn(url, result_value, result_email_type)
                elif result_type == "form":
                    out += f" → {result_value} ✓ written to forms_found.csv"
                    write_form_fn(url, result_value)
                else:
                    out += " → skipped"
                print(out)
            else:
                if result_type == "email":
                    if all_emails and write_all_emails_fn:
                        write_all_emails_fn(url, all_emails)
                    else:
                        write_email_fn(url, result_value, result_email_type)
                elif result_type == "form":
                    write_form_fn(url, result_value)

            if self.count >= self.max_pages:
                break

            for link in self._extract_links(resp.text, url):
                if link not in self.visited:
                    self.queue.append(link)

            time.sleep(self.delay)
