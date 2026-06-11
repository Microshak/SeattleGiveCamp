# Seattle GiveCamp Nonprofit Email Outreach

An automated email outreach system for Seattle GiveCamp that sends personalized HTML emails to nonprofit organizations using data from Google Sheets, with built-in tracking and filtering capabilities.

## 🎯 Overview

This Python-based automation tool helps Seattle GiveCamp organizers efficiently reach out to nonprofit organizations. It:

- Reads nonprofit contact data from Google Sheets
- Sends personalized HTML email campaigns with inline images
- Tracks outreach activity automatically
- Filters out previously contacted organizations
- Supports multiple email profiles (volunteers, sponsors, donors)
- Includes rate limiting to avoid email throttling

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Google Sheets Integration** | Pulls contact data and logs outreach automatically |
| **Template-Based Emails** | HTML email templates with customizable content |
| **Smart Filtering** | Excludes PTA/PTSA organizations and previously contacted nonprofits |
| **Multi-Profile Support** | Separate configurations for volunteers, sponsors, students, etc. |
| **Attachment Support** | Optional PDF attachments (e.g., flyers) |
| **Rate Limiting** | Configurable delays between emails to avoid spam filters |
| **Security-First** | Credentials stored in environment variables, never hardcoded |

---

## 🔧 Prerequisites

- **Python 3.10+**
- **Google Service Account** with Google Sheets API access
- **Gmail account** with App Password enabled
- **Google Sheet** with nonprofit contact information

### Python Dependencies

```bash
pip install gspread google-auth python-dotenv
```

Or install from requirements.txt:

```bash
pip install -r requirements.txt
```

---

## 🚀 Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/Microshak/GMailer.git
cd GMailer
```

### 2. Configure Credentials

Create a Google Service Account and download the JSON credentials file:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable Google Sheets API
4. Create a Service Account
5. Download the JSON key file
6. Rename it to `seattlegivecamp-1373-0bf9a18afc34.json` (or your preferred name)

### 3. Set Up Environment Variables

Create a `.env` file based on your profile:

```bash
# Example: .env.volunteer
GOOGLE_SHEET_URL=https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit
GOOGLE_SHEET_NAME=Charities
OUTREACH_TRACKING_TAB=Outreach Tracking
EMAIL_SUBJECT=Join Seattle GiveCamp 2025!
EMAIL_HTML_FILE=volunteer.html
ATTACHMENT_FILE=Seattle_GiveCamp_Flyer.pdf
SENDER_EMAIL=your.email@gmail.com
SENDER_PASSWORD=your-app-password
SERVICE_ACCOUNT_FILE=seattlegivecamp-1373-0bf9a18afc34.json
DELAY_BETWEEN_EMAILS=300
FILTER=TRUE
```

### 4. Prepare Your Email Template

Place HTML email templates in the `email/` directory:
- `email/volunteer.html` - Volunteer recruitment
- `email/sponsor.html` - Sponsor outreach  
- `email/college.html` - College group outreach
- `email/studentgroup.html` - Student group outreach

### 5. Run the Script

```bash
# Send volunteer outreach emails
python3 send_org_emails.py volunteer

# Send sponsor emails
python3 send_org_emails.py sponsor

# Use default .env configuration
python3 send_org_emails.py
```

---

## 📁 Project Structure

```
GMailer/
├── send_org_emails.py          # Main application script
├── readme.md                   # This file
├── ARCHITECTURE.md             # System architecture documentation
├── AGENTS.md                   # Service account and agent details
├── .gitignore                  # Git ignore patterns
├── LICENSE                     # Project license
│
├── email/                      # HTML email templates
│   ├── email.html             # Default template
│   ├── volunteer.html         # Volunteer recruitment
│   ├── sponsor.html           # Sponsor outreach
│   ├── college.html           # College groups
│   ├── studentgroup.html      # Student groups
│   ├── v1d.html              # Variant 1 (donors)
│   └── v1m.html              # Variant 1 (members)
│
├── assets/                     # Attachments and images
│   ├── sgc.png                # Inline logo (required)
│   └── Seattle_GiveCamp_Flyer.pdf  # Optional attachment
│
└── .env*                       # Environment configurations (not in git)
    ├── .env                   # Default configuration
    ├── .env.volunteer         # Volunteer profile
    ├── .env.v1d               # Donor variant 1
    └── .env.v1m               # Member variant 1
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_SHEET_URL` | Yes | - | Full URL of your Google Sheet |
| `GOOGLE_SHEET_NAME` | Yes | - | Name of the worksheet with contact data |
| `OUTREACH_TRACKING_TAB` | Yes | - | Name of worksheet for logging sent emails |
| `EMAIL_SUBJECT` | Yes | - | Subject line for emails |
| `EMAIL_HTML_FILE` | Yes | - | HTML template filename (in `email/` folder) |
| `ATTACHMENT_FILE` | No | - | PDF attachment filename (in `assets/` folder) |
| `SENDER_EMAIL` | Yes | - | Gmail address for sending |
| `SENDER_PASSWORD` | Yes | - | Gmail App Password (not regular password) |
| `SERVICE_ACCOUNT_FILE` | Yes | - | Path to Google service account JSON |
| `DELAY_BETWEEN_EMAILS` | No | 300 | Seconds between emails (5 minutes) |
| `FILTER` | No | TRUE | Apply name-based filtering (PTA/religious/etc.) |

### Google Sheet Structure

Your **Charities** sheet should have at minimum:
- `Name` column - Organization name
- `Email` column - Contact email address

Your **Outreach Tracking** sheet should have:
- Column A: Organization name
- Column B: Sender name (hardcoded as "Mike")
- Column C: Email address

---

## 🔐 Security Best Practices

- **Never commit `.env` files or credentials** - they are in `.gitignore`
- **Use Gmail App Passwords**, not your regular Gmail password
- **Keep service account JSON secure** - treat it like a password
- **Rotate credentials** periodically
- **Limit Google Sheet access** to only necessary users

See [AGENTS.md](AGENTS.md) for detailed agent credential information.

---

## 📊 Usage Examples

### Example 1: Send Volunteer Recruitment Emails

```bash
python3 send_org_emails.py volunteer
```

Uses `.env.volunteer` configuration to send volunteer recruitment emails to uncontacted nonprofits.

### Example 2: Send Sponsor Outreach

```bash
python3 send_org_emails.py sponsor
```

Uses `.env.sponsor` configuration for sponsor/partner outreach.

### Example 3: Disable Filtering for Specific Campaign

Set `FILTER=FALSE` in your `.env` file to send to all uncontacted organizations (still excludes previously contacted).

### Example 4: Custom Delay Between Emails

```bash
# In .env file
DELAY_BETWEEN_EMAILS=600  # 10 minutes between emails
```

---

## 🔍 Filtering Logic

The system automatically filters out:

1. **Previously contacted** organizations (tracked in Outreach Tracking sheet)
2. **PTA/PTSA organizations** and other excluded categories when `FILTER=TRUE`:
   - Religious organizations (church, temple, ministry)
   - Schools and education groups (school, college, academy)
   - Sports clubs (soccer, tennis, baseball)
   - Community groups (PTA, PTO, Kiwanis)
   - And more (see `stop_words` in `send_org_emails.py`)

To view or modify the filter list, edit the `stop_words` array in `send_org_emails.py`.

---

## 🛠️ Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| **Authentication failed** | Check your Gmail App Password is correct and 2FA is enabled |
| **Google Sheets API error** | Verify service account has access to the sheet (Share with service account email) |
| **Module not found** | Run `pip install gspread google-auth python-dotenv` |
| **No emails sent** | Check FILTER setting and Outreach Tracking sheet for existing contacts |
| **Emails in spam** | Increase DELAY_BETWEEN_EMAILS and verify sender reputation |

### Getting a Gmail App Password

1. Enable 2-Factor Authentication on your Gmail account
2. Go to Google Account > Security > 2-Step Verification > App passwords
3. Generate an app password for "Mail"
4. Use this password in `SENDER_PASSWORD` (not your regular password)

### Granting Sheet Access to Service Account

1. Open your Google Sheet
2. Click "Share"
3. Add the service account email (found in the JSON file's `client_email` field)
4. Give "Editor" permissions

---

## 🏗️ Architecture

For detailed system architecture, component diagrams, and data flow, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

### Development Tips

- Test with `FILTER=FALSE` and a small test sheet first
- Use a test Gmail account for development
- Check `email/` folder for HTML template examples
- Review `send_org_emails.py` for customization points

---

## 📄 License

This project is licensed under the terms in the [LICENSE](LICENSE) file.

---

## 🆘 Support

For issues or questions:
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for technical details
- Check [AGENTS.md](AGENTS.md) for credential setup
- Open an issue on GitHub

---

**Note:** This is a volunteer coordination tool for Seattle GiveCamp. Please use responsibly and respect recipient privacy and preferences.