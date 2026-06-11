import re

from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

LOCAL_SPONSOR = re.compile(r"^(sponsor|partner|donate|support|events|membership)", re.I)
LOCAL_GENERAL = re.compile(r"^(info|contact|hello|team|inquiries|general)", re.I)
LOCAL_ADMIN = re.compile(r"^(admin|office)", re.I)
LOCAL_NOREPLY = re.compile(r"^(noreply|no.reply|unsubscribe)", re.I)
LOCAL_DOT = re.compile(r"^[a-zA-Z]+\.[a-zA-Z]+")

CONTEXT_SPONSOR = re.compile(r"\bsponsor(ship|ed|ing)?\b", re.I)
CONTEXT_PARTNER = re.compile(r"\bpartner(ship)?\b", re.I)
CONTEXT_DONATE = re.compile(r"\b(donate|donation|support(\s+us)?)\b", re.I)
CONTEXT_CONTACT = re.compile(r"\b(contact|get(\s+)?in(\s+)?touch|reach(\s+)?out)\b", re.I)

CONTEXT_WIDTH = 200


class Analyzer:
    def __init__(self, llm_analyzer=None):
        self.llm = llm_analyzer

    def analyze_page(self, url: str, text: str, html: str = "") -> dict:
        all_emails = self._extract_all(text)

        best = self._best(all_emails)
        if best:
            return {
                "type": "email",
                "value": best["email"],
                "email_type": best["type"],
                "all_emails": [
                    {"email": e["email"], "type": e["type"]}
                    for e in all_emails
                    if e["score"] > -1000
                ],
            }

        form_result = self._detect_form(url, text, html)
        if form_result:
            return form_result

        return {"type": "none", "value": ""}

    def _extract_all(self, text: str) -> list[dict]:
        matches = []
        for m in EMAIL_RE.finditer(text):
            email = m.group()
            start = m.start()
            end = m.end()
            local = email.split("@")[0]
            before = text[max(0, start - CONTEXT_WIDTH):start]
            after = text[end:end + CONTEXT_WIDTH]
            score, type_ = self._score(local, before, after)
            matches.append({
                "email": email,
                "local": local,
                "before": before.strip(),
                "after": after.strip(),
                "score": score,
                "type": type_,
            })
        return matches

    def _score(self, local: str, before: str, after: str) -> tuple[int, str]:
        score = 0
        type_ = "fallback"

        if LOCAL_NOREPLY.search(local):
            return (-1000, "ignored")

        if LOCAL_SPONSOR.search(local):
            score += 100
            type_ = "sponsorship"
        elif LOCAL_GENERAL.search(local):
            score += 20
            type_ = "general"
        elif LOCAL_ADMIN.search(local):
            score += 10
            type_ = "general"

        context = before + " " + after
        if CONTEXT_SPONSOR.search(context):
            score += 80
            type_ = "sponsorship"
        if CONTEXT_PARTNER.search(context):
            score += 60
            if type_ != "sponsorship":
                type_ = "sponsorship"
        if CONTEXT_DONATE.search(context):
            score += 40
            if type_ == "fallback":
                type_ = "general"
        if CONTEXT_CONTACT.search(context):
            score += 10
            if type_ == "fallback":
                type_ = "general"

        if LOCAL_DOT.match(local):
            score -= 10

        return (score, type_)

    def _best(self, emails: list[dict]) -> dict | None:
        valid = [e for e in emails if e["score"] > -1000]
        if not valid:
            return None
        valid.sort(key=lambda e: e["score"], reverse=True)
        return valid[0]

    def _detect_form(self, url: str, text: str, html: str) -> dict | None:
        if html:
            soup = BeautifulSoup(html, "html.parser")
            for form in soup.find_all("form"):
                action = form.get("action", "")
                combined = action + " " + form.get_text()
                if CONTEXT_SPONSOR.search(combined):
                    return {"type": "form", "value": f"{url} #{action}" if action else url}

            for a in soup.find_all("a", href=True):
                link_text = a.get_text()
                href = a["href"]
                if CONTEXT_SPONSOR.search(link_text) and ("contact" in href or "form" in href):
                    return {"type": "form", "value": href}

        if self.llm:
            try:
                return self.llm.analyze_page(url, text)
            except Exception:
                pass

        return None
