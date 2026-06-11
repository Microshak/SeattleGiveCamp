# mikeTODO.md — GiveCamp Sponsorship Agent

> Fill this out before handing back to the LLM. Every blank here is a blocker.
> Once complete, the LLM can generate all config files and finalize the agent.

---

## SECTION 1: Organization Identity

These go into `givecamp_profile.yaml`.

```yaml
org_legal_name: "Seattle GiveCamp"              # e.g. "Seattle GiveCamp" or the registered legal name
org_type: "501(c)(3) nonprofit"                    # e.g. "501(c)(3) nonprofit"
ein: "47-2723225"                         # Federal Tax ID / EIN (format: XX-XXXXXXX)
website: "https://seattlegivecamp.org"
year_founded: "2011"                # e.g. 2009
state_of_incorporation: "Washington"      # e.g. "Washington"
```

---

## SECTION 2: Primary Contact

Who sponsors should reach out to / who the form submissions come from.

```yaml
contact_name: "Mike Roshak"                # Full name
contact_title: "Membership Coordinator"               # e.g. "Executive Director" or your title
contact_email: "michael@seattlegivecamp.org"               # The email sponsors will see
contact_phone: "(425) 405-0301"               # Optional but many forms require it
mailing_address:
  street: "26226 131st pl se"
  city: "Kenat"
  state: "WA"
  zip: "98030"
```

---

## SECTION 3: Event Details

```yaml
event_name: "Seattle GiveCamp"
event_location: "Redmond WA"              # e.g. "Seattle, WA" or specific venue
event_date_2026: "October 17th, 2026"             # Approximate date or month of next event
nonprofits_served_per_year: "8"  # e.g. 15
volunteers_per_year: "100"         # e.g. 200
years_running: "15"               # How many annual events have been held
```

---

## SECTION 4: Mission & Impact Statements

These are used to fill open-text fields on forms. Write them now so the LLM
doesn't improvise. Keep each to the length described.

```yaml
mission_one_sentence: "To provide pro bono software development to Seattle-area non-profits."
# Example: "Seattle GiveCamp connects nonprofits with volunteer technologists
# for a weekend of free web and software development."

mission_paragraph: "Seattle GiveCamp is a volunteer-led, registered 501(c)(3) nonprofit organization dedicated to providing pro bono software development and technology solutions to Seattle-area charities. By hosting high-impact, weekend-long hackathons, the organization brings together local software developers, designers, database administrators, and project managers to build websites, mobile apps, and custom database tools for nonprofits that lack dedicated tech budgets. Since 2011, Seattle GiveCamp has supported over 150 local organizations, transforming community goodwill into functional digital tools and delivering hundreds of thousands of dollars in professional technical services back into the regional nonprofit ecosystem."
# 3-4 sentences. What you do, who you serve, why it matters.

impact_statement: "Seattle GiveCamp bridges the tech equity gap by translating professional technical skills into operational capacity for community nonprofits. Local charities often face steep financial barriers when adopting new technologies, which diverts scarce resources away from their core missions. By mobilizing a localized network of tech professionals, Seattle GiveCamp solves this problem through concentrated weekend hackathons.Key Impact Metrics150+ Charities Empowered: Over a decade of consistent service, optimizing operational efficiency for small-to-medium regional nonprofits.$500,000+ Injected Annually: Hundreds of hours of pro bono developer, designer, and project management labor are delivered directly into the local economy every year.100% Retained Funding: Every digital solution provided allows the receiving charities to keep their funding focused on front-line community services rather than expensive IT overhead.Scalable Solutions DeliveredThe hackathon outputs go beyond temporary assistance, providing permanent infrastructure to optimize how regional nonprofits run:Custom Database Architecture: Organizes donor lists and streamlines volunteer tracking for better organizational outreach.Mobile Applications: Builds front-facing tools that help charities connect directly with the vulnerable populations they serve.Modernized Web Ecosystems: Creates secure, responsive websites that increase local fundraising capacity and digital visibility."
# Quantified. Example: "Since 2009, Seattle GiveCamp has delivered over $X
# in free technology services to Y nonprofits, mobilizing Z volunteers annually."

value_to_sponsor_short: "ponsoring Seattle GiveCamp offers your company high-impact brand visibility among hundreds of local tech professionals while fulfilling your corporate social responsibility goals. Your investment directly funds the creation of vital digital infrastructure for regional charities, turning corporate sponsorship into tangible community empowerment."
# 1-2 sentences. Why should a company sponsor you?

value_to_sponsor_long: "Sponsoring Seattle GiveCamp positions your company at the center of the Pacific Northwest tech community, delivering exceptional brand visibility to hundreds of local developers, designers, and industry leaders. By backing our high-impact hackathons, your organization generates immense community goodwill, as your investment directly funds the digital infrastructure that regional charities need to scale their vital services. Furthermore, it offers a powerful employee engagement angle, providing your tech talent with a fulfilling corporate social responsibility opportunity to collaborate, sharpen their skills, and give back locally. Ultimately, your partnership transforms corporate sponsorship into a measurable, lasting impact on both local tech culture and regional nonprofit success."
# 3-5 sentences. Full pitch. Include brand visibility, community goodwill,
# employee engagement angle, etc.
```

---

## SECTION 5: Sponsorship Tiers

List your current sponsorship tiers so the agent knows what to request.

```yaml
sponsorship_tiers:
  - name: "Platinum"       # e.g. "Gold"
    amount: "$5,000"       # e.g. "$5,000"
    benefits: "Premier logo placement on website and event materials, dedicated recruiting table, opportunity for 5-minute opening remarks, logo on event T-shirts, recognition in all social media and press releases"
    # 1 available

  - name: "Gold"           # e.g. "Silver"
    amount: "$2,500"
    benefits: "Logo on website and event materials, recruiting table, logo on event T-shirts, recognition in social media and press releases"
    # 2 available

  - name: "Silver"         # e.g. "Bronze"
    amount: "$1,000"
    benefits: "Logo on website and event materials, logo on event T-shirts, recognition in social media"
    # 3 available

  - name: "Bronze"
    amount: "$500"
    benefits: "Logo on website, recognition in social media"
    # 4 available

default_tier_to_request: "Gold"    # Which tier the agent asks for by default
```

---

## SECTION 6: Social Media & Additional Links

```yaml
linkedin: "https://www.linkedin.com/company/seattle-givecamp"        # e.g. "https://linkedin.com/company/seattle-givecamp"
youtube: "https://www.youtube.com/user/SeattleGiveCamp"         # or X handle
facebook: ""
github: ""          # if applicable
sponsorship_deck_url: "http://microshak.com/pitchdeck"   # URL or local path to PDF sponsorship deck
                           # (Leave blank if you don't want the agent
                           #  to attempt file uploads)
```

---

## SECTION 7: Target Company List — Google Sheet Pull

Instead of a manual list, the agent pulls targets from the **Google Sheet** (same one used by the email outreach system).

### Google Sheet Connection

```yaml
google_sheet:
  url: "https://docs.google.com/spreadsheets/d/1B4YouiAPKy_kRUdYcjxtpPk7zKpdURdoSncXSNjIFc0/edit?usp=sharing"
  service_account_file: "../GMailer/seattlegivecamp-1373-0bf9a18afc34.json"
  forms_tab: "Forms"          # Tab with target companies
  tracking_tab: "Tracking"    # Tab to record completed submissions
```

### Forms Tab Layout

Create a **"Forms"** tab in the Google Sheet with these columns (header row required):

| Company | URL | Notes |
|---------|-----|-------|
| Acme Corp | https://acme.com/community | Has a grants page at /grants |
| ... | ... | ... |

### Tracking Tab Layout

The **"Tracking"** tab logs what's been completed (same tab used by the email outreach system):

| Column | Content |
|--------|---------|
| A | Company name |
| B | Agent name (e.g. "Mike") |
| C | Company URL (or email if applicable) |

### Dedup / Skip Logic

**Important:** Before submitting a form for a company, the agent MUST check the **Tracking** tab to see if that company's URL already appears in column C. If it does, skip that company entirely. This lets you:

1. Add new companies to the **Forms** tab and re-run
2. Already-submitted companies are automatically skipped
3. Update notes on existing entries without double-submitting

When a form is successfully submitted, append a row to the **Tracking** tab:

```yaml
tracking_row: [company_name, "Mike", company_url]
```

---

## SECTION 8: Agent Behavior Decisions

Answer these so the LLM can finalize the agent logic.

**Q1: Default sponsorship tier**
When a form has a dropdown for sponsorship level, what should the agent pick?
```
Answer: Bronze_______________________________________________
```

**Q2: PDF sponsorship deck**
If a form has a file upload field, should the agent try to attach your sponsorship deck PDF?
- [ ] Yes — attach the PDF at `sponsorship_deck_url` above
- [ ] No — skip file upload fields

**Q3: "How did you hear about us" fields**
What should the agent answer for these?
```
Answer: Web search
```

**Q4: W-9 / Financial document requests**
If a form requires a W-9 or other IRS document upload, should the agent:
- [X] Skip this company and log as "requires documents"
- [ ] Attach a W-9 (provide path to file: _______________)

**Q5: Run summary report**
After each run, where should results go?
- [X] Just SQLite log (check it manually)
- [X] Email me a summary at: micheal@seattlegivecamp.org_______________________________________________
- [ ] Both

**Q6: High-priority companies**
Any companies in the target list that need a custom note or specific ask?

```
No
```

**Q7: Boilerplate for "anything else you'd like to share" fields**
Some forms have a free-text catch-all at the end. What should the agent write?
```
No
```

---

## SECTION 9: Technical Config

```
# .env values
LLM_BASE_URL=http://localhost:8080/v1
LLM_MODEL=qwen3.5-35b-a3b

# Confirm these are correct for your setup:
PLAYWRIGHT_HEADLESS=true        # Set to false if you want to watch it run
LOG_DB_PATH=./logs/submissions.db
SCREENSHOT_DIR=./screenshots
```

---

## DONE CHECKLIST

Before handing back to the LLM, confirm:

- [ ] Section 1 — Org identity complete (EIN is the most commonly missed)
- [ ] Section 2 — Contact info complete
- [ ] Section 3 — Event details complete
- [ ] Section 4 — All 5 mission/pitch text blocks written
- [ ] Section 5 — Sponsorship tiers listed, default tier chosen
- [ ] Section 6 — Social links added, sponsorship deck decision made
- [ ] Section 7 — At least 5 target companies listed with URLs
- [ ] Section 8 — All 7 behavior questions answered
- [ ] Section 9 — Technical config confirmed

**When this file is complete, hand it back to the LLM with this prompt:**

> "mikeTODO.md is filled out. Generate givecamp_profile.yaml, targets.yaml,
> and prompts.yaml from it, then proceed with full implementation per the PRD."
