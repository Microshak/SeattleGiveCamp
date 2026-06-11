"""
Playwright engine — navigates company websites, finds sponsorship/contact forms,
fills them using LLM guidance, and submits.

Architecture:
  1. Navigate to target URL
  2. Search for sponsorship-related links (nav, footer, body)
  3. Follow the best candidate link(s) to reach a form page
  4. Extract form HTML, send to LLM for analysis
  5. Fill identified fields using Playwright
  6. Optionally validate, then submit
  7. Screenshot confirmation
"""

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from config import Settings
from llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── Keywords that suggest a sponsorship/partnership/community page ──────
SPONSORSHIP_KEYWORDS = [
    "sponsor", "partner", "donate", "community", "giving", "support",
    "foundation", "corporate", "contact", "about", "inquiry",
]

# ── Keywords that suggest we should NOT try this link ───────────────────
SKIP_KEYWORDS = [
    "privacy", "terms", "cookie", "career", "job", "investor",
    "login", "sign in", "register", "account",
]

# ── Max pages to visit per company while searching for a form ────────────
MAX_SEARCH_PAGES = 5


@dataclass
class FormResult:
    """Outcome of attempting to fill a form for one company."""
    company_name: str
    company_url: str
    success: bool = False
    form_url: str = ""
    form_purpose: str = ""
    status: str = ""  # submitted | requires_w9 | no_form_found | skipped | error
    error_message: str = ""
    screenshot_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FormFiller:
    """Core engine — uses Playwright + LLM to find, fill, and submit forms."""

    def __init__(self, settings: Settings, llm: LLMClient):
        self.settings = settings
        self.llm = llm
        self.headless = settings.playwright_headless
        self.screenshot_dir = Path(settings.screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.contact = settings.contact
        self.org = settings.org
        self.default_tier = settings.default_tier
        self.sponsorship_deck_url = settings.sponsorship_deck_url
        self.attach_deck = settings.behavior.attach_sponsorship_deck
        self.skip_on_w9 = settings.behavior.skip_on_w9_required

    def process_company(self, company_name: str, company_url: str) -> FormResult:
        """
        Main entry: navigate to company_url, find a form, fill it, submit.

        Returns a FormResult with the outcome.
        """
        result = FormResult(company_name=company_name, company_url=company_url)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()

            try:
                # ── Step 1: Navigate to the target URL ─────────────────────
                logger.info("Navigating to %s", company_url)
                try:
                    page.goto(company_url, wait_until="domcontentloaded", timeout=30000)
                except PlaywrightTimeout:
                    logger.warning("Timeout loading %s, continuing with partial load.", company_url)
                except Exception as e:
                    result.status = "error"
                    result.error_message = f"Navigation failed: {e}"
                    return result

                time.sleep(2)  # let JS-rendered content settle

                # ── Step 2: Find a sponsorship/contact form ─────────────────
                form_page = self._find_form_page(page, company_url, result)
                if form_page is None:
                    result.status = "no_form_found"
                    self._screenshot(page, company_name, "no_form")
                    return result

                # ── Step 3: Extract forms on the current page ───────────────
                forms = self._extract_forms(page)
                if not forms:
                    result.status = "no_form_found"
                    self._screenshot(page, company_name, "no_form")
                    return result

                # ── Step 4: Pick the most relevant form and fill it ─────────
                best_form_html = self._pick_best_form(forms)
                analysis = self.llm.analyze_form(best_form_html)

                if not analysis.get("should_submit", False):
                    reasoning = analysis.get("reasoning", "")
                    if "w9" in reasoning.lower() or "w-9" in reasoning.lower():
                        result.status = "requires_w9"
                    else:
                        result.status = "skipped"
                        result.error_message = reasoning
                    self._screenshot(page, company_name, "skipped")
                    return result

                result.form_purpose = analysis.get("form_purpose", "unknown")

                # ── Step 5: Fill the fields ────────────────────────────────
                self._fill_fields(page, analysis.get("fields", []))

                self._screenshot(page, company_name, "filled")

                # ── Step 6: Validate before submit (optional LLM check) ─────
                validation = self.llm.validate_submission(
                    analysis.get("fields", []),
                    result.form_purpose,
                    company_url,
                )
                if not validation.get("ok_to_submit", True):
                    issues = validation.get("issues", [])
                    logger.warning("Pre-submit validation flagged issues: %s", issues)
                    # Continue anyway — validation is advisory

                # ── Step 7: Click submit ────────────────────────────────────
                submit_selector = analysis.get("submit_selector", "")
                if submit_selector:
                    try:
                        page.click(submit_selector, timeout=5000)
                        time.sleep(3)
                        result.success = True
                        result.status = "submitted"
                        self._screenshot(page, company_name, "submitted")
                    except Exception as e:
                        # Try generic submit button
                        try:
                            page.click("button[type='submit']", timeout=5000)
                            time.sleep(3)
                            result.success = True
                            result.status = "submitted"
                            self._screenshot(page, company_name, "submitted")
                        except Exception:
                            result.status = "error"
                            result.error_message = f"Submit click failed: {e}"
                            self._screenshot(page, company_name, "submit_error")
                else:
                    # No submit selector — try generic
                    try:
                        page.click("button[type='submit']", timeout=5000)
                        time.sleep(3)
                        result.success = True
                        result.status = "submitted"
                        self._screenshot(page, company_name, "submitted")
                    except Exception:
                        result.status = "error"
                        result.error_message = "No submit button found"
                        self._screenshot(page, company_name, "no_submit")

            except Exception as e:
                logger.exception("Unexpected error processing %s: %s", company_name, e)
                result.status = "error"
                result.error_message = str(e)
                try:
                    self._screenshot(page, company_name, "error")
                except Exception:
                    pass

            finally:
                context.close()
                browser.close()

        return result

    # ── Internal: form discovery ────────────────────────────────────────────

    def _find_form_page(self, page: Page, base_url: str, result: FormResult) -> Page | None:
        """
        Search the current page and nearby pages for a sponsorship/contact form.
        Returns the page with the form, or None.
        """
        visited = set()
        pages_to_check = [(page, base_url)]
        pages_checked = 0

        while pages_to_check and pages_checked < MAX_SEARCH_PAGES:
            current_page, current_url = pages_to_check.pop(0)
            normalized = self._normalize_url(current_url)
            if normalized in visited:
                continue
            visited.add(normalized)

            # Check if this page already has a form
            forms = self._extract_forms(current_page)
            if forms:
                result.form_url = current_page.url
                return current_page

            # Collect links from the page
            links = self._get_page_links(current_page)
            candidates = self._rank_links(links, base_url)

            if candidates and pages_checked < MAX_SEARCH_PAGES - 1:
                # Try the best candidate
                best = candidates[0]
                logger.info("Following candidate link: %s → %s", current_url, best["url"])
                try:
                    current_page.goto(best["url"], wait_until="domcontentloaded", timeout=20000)
                    time.sleep(2)
                    pages_checked += 1
                    pages_to_check.append((current_page, best["url"]))
                except Exception as e:
                    logger.warning("Failed to follow link %s: %s", best["url"], e)
                    pages_checked += 1
                    # Try next candidates
                    for c in candidates[1:2]:  # just try one more
                        try:
                            current_page.goto(c["url"], wait_until="domcontentloaded", timeout=20000)
                            time.sleep(2)
                            pages_checked += 1
                            pages_to_check.append((current_page, c["url"]))
                            break
                        except Exception:
                            pages_checked += 1
            else:
                pages_checked += 1

        return None

    def _get_page_links(self, page: Page) -> list[dict]:
        """Extract all meaningful links from the current page."""
        try:
            links = page.evaluate("""() => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.getAttribute('href');
                    const text = (a.textContent || '').trim().substring(0, 100);
                    if (href && !href.startsWith('#') && !href.startsWith('mailto:') &&
                        !href.startsWith('tel:') && !href.startsWith('javascript:')) {
                        links.push({url: href, text: text});
                    }
                });
                return links;
            }""")
            return links
        except Exception:
            return []

    def _rank_links(self, links: list[dict], base_url: str) -> list[dict]:
        """Rank links by relevance to sponsorship/contact. Return sorted list."""
        scored = []
        for link in links:
            text_lower = (link.get("text", "") + " " + link.get("url", "")).lower()
            score = 0

            for kw in SPONSORSHIP_KEYWORDS:
                if kw in text_lower:
                    score += 10

            # Boost exact matches
            if "sponsor" in text_lower:
                score += 20
            if "partner" in text_lower:
                score += 15
            if "community" in text_lower:
                score += 10

            # Penalize skip keywords
            for kw in SKIP_KEYWORDS:
                if kw in text_lower:
                    score -= 30

            # Resolve relative URLs
            url = link["url"]
            if not url.startswith(("http://", "https://")):
                url = urljoin(base_url, url)

            # Only include same-domain links
            if urlparse(url).netloc != urlparse(base_url).netloc:
                continue

            if score > 0:
                scored.append({"url": url, "text": link.get("text", ""), "score": score})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    # ── Internal: form extraction ───────────────────────────────────────────

    def _extract_forms(self, page: Page) -> list[str]:
        """Extract all form elements' HTML from the current page."""
        try:
            forms = page.evaluate("""() => {
                const forms = document.querySelectorAll('form');
                return Array.from(forms).map(f => f.outerHTML.substring(0, 8000));
            }""")
            return [f for f in forms if f and len(f) > 50] if forms else []
        except Exception:
            return []

    def _pick_best_form(self, forms: list[str]) -> str:
        """Pick the most promising form (longest one, most likely sponsorship)."""
        # Simple heuristic: prefer forms with "sponsor" or longer forms
        for form_html in forms:
            if "sponsor" in form_html.lower():
                return form_html
        return max(forms, key=len)

    # ── Internal: field filling ─────────────────────────────────────────────

    def _fill_fields(self, page: Page, fields: list[dict]):
        """Fill form fields based on LLM analysis."""
        for field in fields:
            selector = field.get("selector", "")
            field_type = field.get("field_type", "text")
            value = field.get("value", "")
            confidence = field.get("confidence", 0.0)

            if not selector or confidence < 0.3:
                continue

            # Skip file uploads unless explicitly configured
            if field_type == "file":
                if not self.attach_deck:
                    continue
                # Would use page.set_input_files(selector, path)
                continue

            try:
                if field_type == "select":
                    # Try to select by value or label
                    try:
                        page.select_option(selector, value=value, timeout=3000)
                    except Exception:
                        try:
                            page.select_option(selector, label=value, timeout=3000)
                        except Exception:
                            logger.debug("Could not select option '%s' in %s", value, selector)
                elif field_type == "checkbox":
                    if value and value.lower() in ("true", "yes", "1", "check"):
                        try:
                            page.check(selector, timeout=3000)
                        except Exception:
                            logger.debug("Could not check %s", selector)
                elif field_type == "radio":
                    try:
                        page.check(selector, timeout=3000)
                    except Exception:
                        logger.debug("Could not select radio %s", selector)
                elif field_type == "textarea":
                    try:
                        page.fill(selector, str(value), timeout=3000)
                    except Exception:
                        logger.debug("Could not fill textarea %s", selector)
                else:
                    # text, email, phone, etc.
                    try:
                        page.fill(selector, str(value), timeout=3000)
                    except Exception:
                        logger.debug("Could not fill %s", selector)
            except Exception as e:
                logger.debug("Field fill error [%s]: %s", selector, e)

    # ── Utilities ───────────────────────────────────────────────────────────

    def _screenshot(self, page: Page, company_name: str, stage: str):
        """Take a screenshot for debugging/audit."""
        try:
            safe_name = "".join(c if c.isalnum() else "_" for c in company_name)[:40]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_name}_{stage}_{timestamp}.png"
            filepath = self.screenshot_dir / filename
            page.screenshot(path=str(filepath), full_page=True)
            logger.info("Screenshot saved: %s", filepath)
        except Exception as e:
            logger.warning("Screenshot failed: %s", e)

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
