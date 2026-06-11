import os
from pathlib import Path
import msal
import requests
from dotenv import load_dotenv
import pickle

dotenv_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=dotenv_path)

CLIENT_ID = os.getenv("Application_id")
TENANT_ID = os.getenv("Tenant_id")
USER_EMAIL = os.getenv("email_address")

SCOPES = ["Mail.Send"]

CACHE_FILE = "token_cache.bin"

# -----------------------------
# Load token cache from disk
# -----------------------------
cache = msal.SerializableTokenCache()

if os.path.exists(CACHE_FILE):
    cache.deserialize(open(CACHE_FILE, "r").read())

app = msal.PublicClientApplication(
    CLIENT_ID,
    authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    token_cache=cache,
)

accounts = app.get_accounts()

result = None

# -----------------------------
# Try silent login first
# -----------------------------
if accounts:
    result = app.acquire_token_silent(SCOPES, account=accounts[0])

# -----------------------------
# If no cached token, do device login
# -----------------------------
if not result:
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        raise RuntimeError(f"Failed to create device flow: {flow}")

    print(flow["message"])

    result = app.acquire_token_by_device_flow(flow)

# -----------------------------
# Save cache back to disk
# -----------------------------
if cache.has_state_changed:
    with open(CACHE_FILE, "w") as f:
        f.write(cache.serialize())

if "access_token" not in result:
    raise RuntimeError(
        f"Token acquisition failed: "
        f"{result.get('error')} — {result.get('error_description')}"
    )

access_token = result["access_token"]

headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
}


def send_email(to_address, subject, body_html):
    url = f"https://graph.microsoft.com/v1.0/users/{USER_EMAIL}/sendMail"

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body_html,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_address
                    }
                }
            ],
        }
    }

    r = requests.post(url, headers=headers, json=payload)

    if r.status_code == 202:
        print("Email sent!")
    else:
        print(f"Error: {r.status_code} — {r.text}")


if __name__ == "__main__":
    send_email(
        to_address="roshak@gmail.com",
        subject="Hello from email3.py",
        body_html="This email was sent from <b>Python</b>!",
    )