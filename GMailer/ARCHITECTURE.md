# Architecture

This document provides an overview of the system architecture for the Seattle GiveCamp Nonprofit Email Outreach project.

---

## Overview

The application automates outreach to nonprofit organizations by sending personalized emails using data from a Google Sheet. It is designed to be run as a script and uses environment variables for configuration and secrets.

---

## Components

### 1. Google Sheets Integration

- **Purpose:** Source of nonprofit contact information and outreach tracking.
- **Access:** Via a Google Service Account 
- **Libraries:** `gspread`, `google-auth`.

### 2. Email Sending

- **Purpose:** Sends HTML emails (with inline images and optional attachments) to filtered nonprofit contacts.
- **SMTP:** Gmail SMTP server (`smtp.gmail.com`).
- **Authentication:** Uses an app password for the sender account.
- **Libraries:** `smtplib`, `email`.

### 3. Configuration and Secrets

- **File:** `.env`
- **Contents:** API keys, credentials, and configuration values.
- **Loading:** Via `python-dotenv`.

### 4. Filtering Logic

- Excludes nonprofits already contacted (tracked in the outreach sheet).
- Excludes organizations with "PTA" or "PTSA" in their name.

---

## Data Flow

1. **Load Configuration:**  
   The script loads environment variables from `.env`.

2. **Authenticate with Google Sheets:**  
   Using the service account, the script reads nonprofit and outreach data.

3. **Filter Contacts:**  
   Removes previously contacted emails and those with "PTA"/"PTSA" in the name.

4. **Send Emails:**  
   For each filtered contact, sends a personalized HTML email with an inline logo and optional attachment.

5. **Delay:**  
   Waits a configurable amount of time between emails to avoid rate limits.

---

## Security

- All secrets and credentials are stored in `.env` and ignored by git.
- Service account credentials are also ignored by git.
- No secrets are hardcoded in the source code.

---

## Deployment

- Designed to run as a command-line script on Linux.
- Requires Python 3.10+ and the listed dependencies in `requirements.txt`.

---

## Extensibility

- Additional filtering or personalization logic can be added in the main script.
- Email templates can be updated in `email.html`.