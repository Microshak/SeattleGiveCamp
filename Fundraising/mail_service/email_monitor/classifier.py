"""
Intent classifier using local LLM via llama.cpp server (OpenAI-compatible API).

Two operating modes:
  1. Classification  — returns structured JSON: intent, confidence, slots, suggested_kb_query
  2. Drafting        — composes a professional email reply using KB context

Temperature is set to 0.0 for deterministic output.  On JSON parse failure
the message is treated as confidence = 0 (escalated).

Requires llama-server running (see FormFillerouter/llm.sh).
"""

import json
import logging
import re
from typing import Optional

from openai import OpenAI

from email_monitor.config import settings

logger = logging.getLogger(__name__)

# ── System prompt: classification mode ───────────────────────────────────

CLASSIFICATION_PROMPT = """You are an email classifier for Seattle GiveCamp, a nonprofit hackathon.
Analyze the email below and return ONLY a valid JSON object — no preamble, no explanation.

Available intents:
  - volunteer_dropout   — person wants to be removed from the volunteer list
  - sponsor_inquiry     — asking about sponsorship tiers, nonprofit status, tax deductibility, etc.
  - event_question      — logistics: dates, location, parking, lunch, tech stack
  - media_inquiry       — press or media interview request
  - general             — other question not covered above
  - unclear             — cannot determine intent

JSON schema:
{
  "intent": "<one of the above>",
  "confidence": <0.0-1.0>,
  "slots": {
    "contact_name": "<string or null>",
    "contact_email": "<string or null>",
    "specific_question": "<string or null>",
    "event_year": "<string or null>"
  },
  "suggested_kb_query": "<a short search query for the knowledge base>",
  "requires_human": true | false
}

Rules:
- confidence < 0.70 → set requires_human = true
- If the email is clearly a volunteer dropout, set intent = "volunteer_dropout"
- If the email asks about sponsorship, set intent = "sponsor_inquiry"
- If the email asks about event logistics, set intent = "event_question"
- For media/press requests, set intent = "media_inquiry" and requires_human = true
- Only use "unclear" if you truly cannot determine the intent
- Be conservative: when in doubt, lower the confidence score"""

# ── System prompt: draft mode ────────────────────────────────────────────

DRAFT_PROMPT = """You are a friendly, professional event coordinator for Seattle GiveCamp.
Draft a reply to the email below using ONLY the information provided in the knowledge base context.
DO NOT invent facts, figures, or policies that are not present in the context.

If the context does not contain enough information to answer the question,
say so honestly and offer to connect the sender with the event owner.

Write in a warm, professional tone.  Sign off with "Best regards, Seattle GiveCamp Team".
Return ONLY the email body — no subject line, no JSON, no explanation."""


class PhiClassifier:
    """Wrapper around local LLM (via llama.cpp server) for classification and drafting."""

    def __init__(self):
        import httpx
        self.client = OpenAI(
            base_url=settings.llm_base_url,
            api_key="not-needed",  # llama.cpp server ignores the key but requires one
            timeout=httpx.Timeout(300.0, connect=10.0),  # 5 min for slow CPU-only LLM
        )
        self.model = settings.llm_model

    # ── Classification ──────────────────────────────────────────────────

    def classify(
        self,
        email_body: str,
        thread_history: Optional[list[dict]] = None,
    ) -> dict:
        """
        Classify an email and return a structured JSON result.

        If thread_history is provided, the last 3 turns are prepended
        to the prompt for multi-turn context awareness.

        Returns a dict matching the classification schema.  On any error,
        returns a safe default with confidence=0.
        """
        # Truncate email body to ~1500 tokens (roughly 6000 chars)
        body = email_body[:6000]

        # Build messages
        messages = [
            {"role": "system", "content": CLASSIFICATION_PROMPT},
        ]

        # Inject thread history (last 3 turns) if available
        if thread_history:
            recent = thread_history[-3:]
            for turn in recent:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": body})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,
                max_tokens=2000,  # Qwen uses ~1000 for thinking on complex prompt, needs room for JSON
                stop=["</think>"],  # Force model to end thinking and produce JSON
                response_format={"type": "json_object"},
            )
            msg = response.choices[0].message
            logger.debug("LLM msg.content=%r, msg.reasoning_content=%r, msg_keys=%s",
                         msg.content, getattr(msg, 'reasoning_content', 'N/A'),
                         [k for k in dir(msg) if not k.startswith('_')])
            # Qwen 3.5 puts thinking in reasoning_content; content may be empty
            raw = (msg.content or "").strip()
            reasoning = getattr(msg, 'reasoning_content', '') or ''
            if not raw and reasoning:
                # If content is empty but reasoning exists, try to extract JSON
                logger.info("Using reasoning_content fallback (len=%d)", len(reasoning))
                raw = reasoning.strip()
            elif not raw:
                logger.error("Both content and reasoning_content are empty! Raw response: %s",
                             response.choices[0].message.model_dump_json()[:500])
            # Strip Qwen's <think>...</think> tokens (in case they leak into content)
            raw = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL)
            # Strip markdown code fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            # Ultimate fallback: find first valid JSON object in raw text
            if raw and raw[0] != '{':
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    raw = match.group(0)
                    # Try to extract just the first complete JSON object
                    # by counting braces to handle nested objects
                    brace_count = 0
                    json_start = -1
                    for i, ch in enumerate(raw):
                        if ch == '{':
                            if brace_count == 0:
                                json_start = i
                            brace_count += 1
                        elif ch == '}':
                            brace_count -= 1
                            if brace_count == 0 and json_start >= 0:
                                raw = raw[json_start:i+1]
                                break
                    logger.info("Extracted JSON via regex fallback (len=%d)", len(raw))
            # Try standard JSON first, then handle common LLM mistakes (single quotes)
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                # Attempt to fix single-quoted JSON (Python-style dicts)
                import ast
                try:
                    result = ast.literal_eval(raw)
                    if isinstance(result, dict):
                        logger.info("Parsed Python-style dict via ast.literal_eval")
                    else:
                        raise ValueError("Not a dict")
                except (ValueError, SyntaxError):
                    # Last resort: try replacing single quotes
                    fixed = raw.replace("'", '"')
                    result = json.loads(fixed)
                    logger.info("Parsed after single-quote fix")

            # Validate required keys
            if "intent" not in result or "confidence" not in result:
                raise ValueError("Missing required keys in classification JSON")

            return result

        except (json.JSONDecodeError, ValueError, Exception) as exc:
            logger.warning("Classification parse failed: %s", exc)
            logger.debug("Raw Phi output: %s", raw if 'raw' in dir() else "N/A")
            return {
                "intent": "unclear",
                "confidence": 0.0,
                "slots": {
                    "contact_name": None,
                    "contact_email": None,
                    "specific_question": None,
                    "event_year": None,
                },
                "suggested_kb_query": "",
                "requires_human": True,
            }

    # ── Drafting ────────────────────────────────────────────────────────

    def draft_reply(
        self,
        kb_context: str,
        original_email: str,
        sender_name: str = "",
    ) -> str:
        """
        Compose a reply email using KB context as the sole source of facts.

        Returns the drafted email body as a plain string.
        """
        prompt = (
            f"Knowledge base context:\n{kb_context}\n\n"
            f"Original email from {sender_name}:\n{original_email}\n"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": DRAFT_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=600,
            )
            draft = response.choices[0].message.content.strip()
            return draft

        except Exception as exc:
            logger.error("Draft generation failed: %s", exc)
            return (
                "Thank you for reaching out to Seattle GiveCamp. "
                "Your inquiry has been received and we will follow up shortly."
            )
