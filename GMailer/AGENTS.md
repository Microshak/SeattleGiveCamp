# Agents

This document describes the agents (service accounts, email senders, and other automated identities) used in this project.

## 1. Google Service Account

- **Purpose:** Access Google Sheets via the Google Sheets API.
- **Credentials File:** `seattlegivecamp-1373-0bf9a18afc34.json`
- **Client Email:** ``
- **Usage:** Loaded in the application via the `SERVICE_ACCOUNT_FILE` environment variable in `.env`.

## 2. Email Sender

- **Purpose:** Sends outreach emails to nonprofits.
- **Email Address:** Defined by `SENDER_EMAIL` in `.env` 
- **Authentication:** Uses an app password stored in `SENDER_PASSWORD` in `.env`
- **SMTP:** Gmail SMTP server (`smtp.gmail.com`)

## 3. Environment Variables

All sensitive agent credentials and configuration are stored in the `.env` file and **should not be committed to version control**.

---

**Note:**  
- Do not share or commit credential files or `.env` to public repositories.
- For more information on each agent, see the relevant section in the