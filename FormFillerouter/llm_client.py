"""
LLM client — communicates with the local llama.cpp server (OpenAI-compatible API).

Uses the prompts from prompts.yaml and the profile from givecamp_profile.yaml
to analyze web forms and determine what values to fill.
"""

import json
import logging
import re

from openai import OpenAI

from config import Settings, build_profile_text

logger = logging.getLogger(__name__)

# Maximum HTML size we send to the LLM (characters) to avoid blowing context window.
MAX_HTML_CHARS = 6000


def _extract_json(raw: str) -> dict:
    """Extract a JSON object from LLM output, handling markdown code fences."""
    # Try to find JSON inside ```json ... ``` blocks
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1)

    # Try to find the first { ... } block
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        raw = brace_match.group(0)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Last resort: strip trailing commas and try again
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM JSON output. Raw: %.300s", raw)
            return {"fields": [], "form_purpose": "none", "should_submit": False,
                    "reasoning": "JSON parse error"}


class LLMClient:
    """Thin wrapper around the OpenAI-compatible local LLM API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model
        self.profile_text = build_profile_text(settings)
        self.client = OpenAI(base_url=self.base_url, api_key="not-needed", timeout=300.0)
        self.default_tier = settings.default_tier
        self.attach_sponsorship_deck = settings.behavior.attach_sponsorship_deck
        self.skip_on_w9 = settings.behavior.skip_on_w9_required

    def _chat(self, system: str, user: str, temperature: float = 0.1, max_tokens: int = 2048) -> str:
        """Send a prompt to the LLM and return the response text.
        Handles thinking models (Qwen3) where content may be empty because
        tokens were consumed by the reasoning/thinking phase."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            msg = response.choices[0].message
            # Qwen3 thinking models: content may be empty if all tokens went to reasoning.
            # Try content first, then reasoning_content, then concatenate both.
            content = (msg.content or "").strip()
            reasoning = getattr(msg, "reasoning_content", None) or ""
            if content:
                return content
            if reasoning:
                # Try to extract JSON from the reasoning (some models embed it there)
                logger.warning("LLM returned empty content; using reasoning_content (len=%d)", len(reasoning))
                return reasoning.strip()
            logger.warning("LLM returned empty response (both content and reasoning_content are empty)")
            return ""
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise

    def analyze_form(self, form_html: str) -> dict:
        """
        Analyze a form's HTML and return a field-filling plan.

        Returns:
            dict with keys: fields (list), form_purpose, submit_selector,
            should_submit, reasoning
        """
        truncated_html = form_html[:MAX_HTML_CHARS]
        prompt = self.settings.prompts.analyze_form.format(
            profile=self.profile_text,
            form_html=truncated_html,
            default_tier=self.default_tier,
        )
        # Inject behavior flags into the prompt
        if self.skip_on_w9:
            prompt += "\nIMPORTANT: If any field mentions W-9, W9, IRS, tax form, or tax document upload, set should_submit to false and note 'requires_w9'."
        if not self.attach_sponsorship_deck:
            prompt += "\nIMPORTANT: Skip any file upload fields. Set their value to empty string."

        raw = self._chat(self.settings.prompts.system, prompt, temperature=0.1, max_tokens=8192)
        result = _extract_json(raw)
        logger.info("Form analysis: purpose=%s, fields=%d, submit=%s",
                     result.get("form_purpose", "?"),
                     len(result.get("fields", [])),
                     result.get("should_submit", False))
        return result

    def find_sponsorship_link(self, current_url: str, page_title: str, links: list[dict]) -> dict:
        """Given a page's links, ask the LLM to pick the best one for sponsorship."""
        links_json = json.dumps(links, indent=2)
        prompt = self.settings.prompts.find_sponsorship_page.format(
            current_url=current_url,
            page_title=page_title,
            links_json=links_json[:4000],
        )
        raw = self._chat(self.settings.prompts.system, prompt, temperature=0.2, max_tokens=4096)
        return _extract_json(raw)

    def validate_submission(self, filled_fields: list[dict], form_purpose: str, company_url: str) -> dict:
        """Validate a filled form before clicking submit."""
        summary_lines = []
        for f in filled_fields:
            label = f.get('label', '?')
            val = f.get('value', '')
            ftype = f.get('field_type', '?')
            summary_lines.append(f"  - {label}: {val} [{ftype}]")
        summary = "\n".join(summary_lines)

        prompt = self.settings.prompts.validate_before_submit.format(
            filled_fields_summary=summary,
            form_purpose=form_purpose,
            company_url=company_url,
        )
        raw = self._chat(self.settings.prompts.system, prompt, temperature=0.1, max_tokens=4096)
        return _extract_json(raw)
