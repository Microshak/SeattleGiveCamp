import json
import sys
from openai import OpenAI


class LLMAnalyzer:
    def __init__(self, base_url: str = "http://localhost:1234/v1", model: str = "phi-4"):
        self.client = OpenAI(base_url=base_url, api_key="lm-studio")
        self.model = model

    def analyze_page(self, url: str, text: str) -> dict:
        prompt = f"""You are analyzing a webpage for sponsorship contact information.

Page URL: {url}

Page text (truncated to 3000 chars):
{text[:3000]}

Answer ONLY with a JSON object in this exact format (no markdown, no explanation):
{{"type": "email", "value": "someone@example.com"}}
or
{{"type": "form", "value": "URL or description of the sponsorship form"}}
or
{{"type": "none", "value": ""}}

Rules:
- "email": only if you find an email address that appears to belong to a sponsorship, partnerships, or events coordinator/contact. Prefer role-specific emails over generic ones.
- "form": only if the page contains or clearly links to a sponsorship application or inquiry form.
- "none": if neither is present.
- Return only one result — prioritize email over form if both exist."""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=80,
            )
            raw = response.choices[0].message.content.strip()
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"type": "none", "value": ""}
        except Exception as e:
            print(f"Fatal: LM Studio unreachable — {e}", file=sys.stderr)
            print("Is LM Studio running with Phi-4 loaded?", file=sys.stderr)
            sys.exit(1)
