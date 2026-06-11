**SEATTLE GIVECAMP**

**Email Monitoring & Response System**

_Product Requirements Document_

Version 1.0 - June 2025

Author: Mike (Fundraising & Volunteer Lead)

| **Status** | **Version** | **Last Updated** | **Classification** |
| ---------- | ----------- | ---------------- | ------------------ |
| Draft      | 1.0         | June 2025        | Confidential       |

# **1\. Executive Summary**

Seattle GiveCamp is an annual nonprofit hackathon that connects volunteer technologists with local charities. As the sole person managing fundraising and volunteer coordination, the event owner faces a significant communication bottleneck during campaign periods: hundreds of inbound emails requiring timely, accurate responses across multiple audience types - sponsors, volunteers, and general inquirers.

This document specifies an automated Email Monitoring and Response System that classifies incoming mail, handles routine requests autonomously using local AI models and semantic search, and escalates novel or complex cases to the event owner via Telegram. The system is architected to minimize cost by routing work to local small language models (SLMs) and vector similarity search before touching any paid API.

**Design philosophy**

Deterministic code handles the majority of volume. Phi (local SLM) handles classification and slot extraction. Milvus handles knowledge base retrieval with no per-query LLM cost. Cloud LLMs are a last resort, used only when local models cannot produce a safe response.

# **2\. Background & Problem Statement**

## **2.1 Current Situation**

The event owner manually monitors a Microsoft 365 Outlook inbox during fundraising and volunteer enrollment periods. Email volume spikes significantly in the 8-12 weeks before the annual event. Common message types include:

- Sponsor inquiries about nonprofit status, tax deductibility (501(c)(3)), and sponsorship tiers
- Volunteer dropouts requesting removal from the attendee list
- Event logistics questions (dates, location, parking, lunch, tech stack)
- Media and press inquiries
- General questions not covered by existing FAQ materials

Manually responding to each email is time-consuming, error-prone, and creates delays that can cost sponsorship commitments. There is currently no system to track multi-turn conversations, maintain context across replies, or route complex questions for human review.

## **2.2 Constraints**

- Single operator - no support staff or volunteers available for email triage
- Budget-sensitive - GiveCamp is a nonprofit; per-query cloud LLM costs must be minimized
- Existing infrastructure - Microsoft 365 / Outlook is already in use; Microsoft Graph API access is established via MSAL with delegated OAuth (device code flow)
- Hardware - local machine with 12 GB VRAM GPU suitable for running Phi and embedding models via Ollama
- Volunteer/sponsor list - currently maintained as a CSV/Excel file

# **3\. Goals & Success Metrics**

## **3.1 Goals**

- Automate resolution of high-frequency, low-complexity email categories without human involvement
- Maintain full conversation context across multi-turn email threads
- Route genuinely novel or sensitive cases to the event owner via Telegram within minutes of receipt
- Keep per-email cloud API cost at or near zero for routine messages
- Produce auditable logs of every classification decision and response sent

## **3.2 Success Metrics**

| **Metric**                     | **Target**              | **Notes**                    |
| ------------------------------ | ----------------------- | ---------------------------- |
| Autonomous resolution rate     | ≥75% of inbound volume  | Remainder escalated          |
| Classification accuracy        | ≥90% on held-out sample | Validated before launch      |
| Time to Telegram alert         | <5 min from receipt     | Polling interval dependent   |
| Cloud LLM calls per 100 emails | <5                      | Edge cases only              |
| False escalation rate          | <15%                    | Human reviews unnecessary    |
| Thread continuity              | 100%                    | No lost conversation context |

# **4\. System Architecture**

## **4.1 Architecture Overview**

The system is organized into five sequential layers. Each layer hands off a structured JSON payload to the next, making the entire pipeline inspectable, testable, and debuggable without runtime ambiguity.

| **Layer**    | **Component**     | **Technology**                 | **Responsibility**                                  |
| ------------ | ----------------- | ------------------------------ | --------------------------------------------------- |
| 1 - Ingest   | Email poller      | Python + MSAL / Graph API      | Poll inbox hourly; fetch unread messages            |
| 1 - Ingest   | Thread resolver   | SQLite                         | Look up conversationId; load prior context          |
| 2 - Classify | Intent classifier | Phi (local via Ollama)         | Return structured JSON: intent + confidence + slots |
| 3 - Route    | Router            | Python if/elif                 | Branch on intent and confidence score               |
| 3 - Route    | KB retriever      | Milvus + sentence-transformers | Cosine similarity search over FAQ embeddings        |
| 4 - Respond  | Template engine   | Python string templates        | Fill known-good response templates                  |
| 4 - Respond  | Draft composer    | Phi (local via Ollama)         | Draft reply using KB context as prompt injection    |
| 5 - Escalate | Telegram relay    | python-telegram-bot            | Alert owner; relay reply back as email              |

## **4.2 Data Flow**

Each email processed by the system follows this path:

- Graph API poller fetches unread messages from the monitored mailbox.
- conversationId is used to look up any prior thread state in SQLite. If found, conversation history is prepended to the classification prompt.
- Phi receives the email body and thread context. It returns a JSON object containing intent, confidence score, extracted slots, and a suggested KB query string.
- The router branches on intent + confidence. Confidence below 0.85 triggers immediate escalation regardless of intent.
- For KB-dependent intents, the suggested query is embedded and a similarity search is run against the Milvus collection. Results above the similarity threshold are injected as context.
- A response is generated (template fill or Phi-composed draft) and sent via Graph API. Thread state and the full interaction log are written to SQLite.
- Escalated cases notify the owner via Telegram with the original email, classification result, and any partial KB matches. The owner's Telegram reply is auto-sent as the email response.

## **4.3 Confidence Routing Thresholds**

**Threshold design rationale**

A hard confidence floor prevents the system from sending poorly-classified auto-responses. It is cheaper to escalate a borderline message than to send a wrong reply that damages a sponsor relationship.

| **Confidence band** | **Action**                                      | **Rationale**                                  |
| ------------------- | ----------------------------------------------- | ---------------------------------------------- |
| ≥0.85               | Auto-handle via intent router                   | High certainty; safe to automate               |
| 0.70-0.84           | KB lookup; Phi drafts; human review flag in log | Moderate certainty; proceed but mark for audit |
| <0.70               | Immediate Telegram escalation                   | Low certainty; do not risk wrong response      |

# **5\. Component Specifications**

## **5.1 Email Ingest (Graph API Poller)**

The poller runs on a scheduled interval (default: 60 minutes) and authenticates using the existing MSAL device code flow OAuth token, refreshing silently when the access token expires.

- Fetches messages from the monitored mailbox folder (Inbox by default, configurable)
- Filters to unread messages only; marks each as read after ingestion to prevent duplicate processing
- Extracts: message ID, conversationId, sender address, sender display name, subject, body (plain text preferred, HTML stripped), received timestamp
- On fetch failure (throttle, auth expiry), logs the error and skips the poll cycle without crashing

## **5.2 Thread State Store (SQLite)**

A lightweight SQLite database persists thread context, classification history, and response logs. Two primary tables are required:

### **threads table**

- thread_id - Microsoft conversationId (primary key)
- contact_email - sender email address
- contact_name - sender display name
- intent_history - JSON array of prior intent classifications
- message_history - JSON array of {role, content, timestamp} pairs
- status - open | resolved | escalated | awaiting_human
- created_at, updated_at - ISO timestamps

### **response_log table**

- log_id - auto-increment primary key
- thread_id - foreign key to threads
- message_id - Graph API message ID
- classification_json - full Phi output stored verbatim
- kb_hits - JSON array of Milvus similarity results
- response_sent - final email body sent
- handler - template | phi_draft | human_relay
- escalated - boolean
- sent_at - ISO timestamp

## **5.3 Intent Classifier (Phi via Ollama)**

Phi is run locally via Ollama and receives a tightly constrained system prompt instructing it to output valid JSON only. The model is not asked to draft responses at this stage.

### **Classification JSON schema**

**Required output format (Phi system prompt enforces this schema)**

{ "intent": "volunteer_dropout | sponsor_inquiry | event_question | media_inquiry | general | unclear", "confidence": 0.0-1.0, "slots": { "contact_name": "string | null", "contact_email": "string | null", "specific_question": "string | null", "event_year": "string | null" }, "suggested_kb_query": "string", "requires_human": true | false }

### **Prompt design principles**

- System prompt specifies the exact JSON schema; no preamble or explanation is permitted in the output
- Email body is truncated to 1,500 tokens before being passed to Phi to prevent context overflow
- Thread history (last 3 turns) is prepended when available to support multi-turn classification
- Temperature is set to 0.0 for deterministic output
- If JSON parsing fails, the message is treated as confidence = 0 and escalated

## **5.4 Knowledge Base & Milvus Retrieval**

The knowledge base (KB) is a curated set of FAQ documents covering GiveCamp's nonprofit status, sponsorship tiers, event logistics, volunteer expectations, and historical frequently asked questions. Milvus provides the vector store for semantic similarity search.

### **KB document structure**

- Each KB entry is a short document (1-3 paragraphs) with a title, category tag, and body text
- Documents are stored as markdown files in a /kb directory and versioned in source control
- Categories: nonprofit_status | sponsorship | logistics | volunteer | general

### **Milvus collection schema**

- Collection name: givecamp_kb
- Fields: doc_id (VARCHAR), title (VARCHAR), category (VARCHAR), body (VARCHAR), embedding (FLOAT_VECTOR, dim=384)
- Index type: IVF_FLAT with cosine metric
- Embedding model: all-MiniLM-L6-v2 via sentence-transformers (runs on CPU; no GPU required for inference)

### **Retrieval logic**

- The suggested_kb_query from Phi is embedded using the same model
- Top-3 results are retrieved; similarity scores below 0.72 are discarded
- If no results exceed the threshold, the handler flags for escalation rather than drafting a response
- KB documents are re-embedded whenever source files change (hash-based change detection)

## **5.5 Intent Handlers**

### **volunteer_dropout**

- Load the volunteer CSV into memory
- Match sender email against the list (case-insensitive)
- If matched: remove the row, write the updated CSV, send a template confirmation email
- If not matched: send a "not found" template and log for manual review
- No LLM call required for this handler

### **sponsor_inquiry**

- Run Milvus retrieval against the nonprofit_status and sponsorship categories
- Inject top KB results into Phi prompt: "Draft a reply to this sponsor inquiry using only the following information: {kb_context}"
- Phi drafts the response; it is sent directly if confidence ≥0.85, otherwise flagged for review
- Standard 501(c)(3) documentation links are appended by template after the Phi draft

### **event_question**

- Run Milvus retrieval against logistics and general categories
- If KB hit ≥0.72: Phi drafts reply with context injection
- If no KB hit: escalate to Telegram with the question text

### **general / unclear**

- Attempt KB retrieval; if hit, draft with Phi
- If no hit or confidence <0.70: escalate to Telegram immediately

## **5.6 Response Composer (Phi Draft Mode)**

When Phi is used to draft a reply, it receives a different system prompt from the classification phase. Draft mode instructs Phi to write a complete, professional email response using only the provided KB context.

- Phi is not permitted to invent facts; the prompt explicitly states it must only use provided context
- Draft output is reviewed for JSON-unsafe characters and then sent as plain text email body
- A standard footer is appended to every sent email: GiveCamp name, website, unsubscribe language
- Emails are sent via Graph API using the existing sender implementation

## **5.7 Telegram Escalation & Relay**

When a message requires human handling, the system sends a structured Telegram message to the owner's bot chat. The message includes all information needed to respond without opening Outlook.

### **Telegram alert format**

- Sender name and email address
- Subject line
- Email body (truncated to 800 characters if long)
- Phi classification result and confidence score
- Any partial KB matches found (title + similarity score)
- Reply instructions: "Reply to this message to send your response as email"

### **Reply relay**

- The Telegram bot listener polls for replies using python-telegram-bot
- When a reply to an escalation message is detected, the reply text is sent as an email response via Graph API
- Thread state in SQLite is updated to resolved with handler = human_relay
- A confirmation message is sent back to the Telegram chat: "✓ Sent to {sender_email}"

# **6\. Non-Functional Requirements**

| **Category**    | **Requirement**                                  | **Detail**                                               |
| --------------- | ------------------------------------------------ | -------------------------------------------------------- |
| Availability    | Best-effort continuous operation                 | Single-machine deployment; no HA required for v1         |
| Latency         | Poll-to-response within poll interval + 3 min    | 60 min polling + ~2 min processing budget                |
| Cost            | Zero recurring cloud LLM cost for routine mail   | All classification and KB retrieval runs locally         |
| Privacy         | Email content stays on local machine             | No email body sent to cloud APIs unless escalated        |
| Durability      | SQLite thread state survives process restarts    | WAL mode enabled; daily backup recommended               |
| Observability   | Structured JSON logs for every processed message | Rotated daily; retained for 90 days                      |
| Maintainability | KB updates require no code changes               | Add/edit markdown files; re-index triggers automatically |

# **7\. Technology Dependencies**

| **Component**   | **Technology**                           | **License / Cost**       | **Purpose**                        |
| --------------- | ---------------------------------------- | ------------------------ | ---------------------------------- |
| Email access    | Microsoft Graph API + MSAL               | Free (M365 subscription) | Send, receive, thread management   |
| SLM inference   | Phi via Ollama                           | Free / MIT               | Classification & response drafting |
| Embedding model | all-MiniLM-L6-v2 (sentence-transformers) | Free / Apache 2.0        | Query and document embeddings      |
| Vector store    | Milvus (Docker)                          | Free / Apache 2.0        | KB semantic similarity search      |
| Thread state    | SQLite 3                                 | Free / public domain     | Conversation history & audit log   |
| Escalation      | python-telegram-bot                      | Free / LGPL              | Owner alert & reply relay          |
| Volunteer list  | CSV / Excel file                         | Existing asset           | Volunteer roster management        |
| Scheduler       | APScheduler or cron                      | Free / MIT               | Hourly polling trigger             |

# **8\. Implementation Phases**

## **Phase 1 - Foundation (Week 1-2)**

- SQLite schema creation and ORM wrapper
- Graph API polling loop integrated with existing sender code
- Phi classification prompt and JSON output validation
- Basic routing logic (volunteer_dropout and escalation paths only)
- Telegram bot setup and escalation alert formatting

## **Phase 2 - KB & Retrieval (Week 3)**

- Milvus Docker deployment and collection initialization
- KB document authoring (initial 20-30 FAQ entries)
- Embedding pipeline: all-MiniLM-L6-v2 + Milvus ingest
- Hash-based KB change detection and re-index trigger
- sponsor_inquiry and event_question handlers with KB retrieval

## **Phase 3 - Response Drafting & Hardening (Week 4)**

- Phi draft mode prompt and response composer
- Template library for high-frequency response types
- Full end-to-end integration test with real email samples
- Confidence threshold tuning against test corpus
- Structured JSON logging and log rotation

## **Phase 4 - Operational Readiness (Pre-launch)**

- Dry-run with shadow mode (classify and log but do not send) for one week
- Review classification accuracy against shadow mode log
- KB gap analysis from escalation rate review
- Telegram relay end-to-end test
- SQLite backup automation

# **9\. Open Questions & Decisions Needed**

| **Question**              | **Options**                                                                         | **Decision needed by** |
| ------------------------- | ----------------------------------------------------------------------------------- | ---------------------- |
| Which Phi model variant?  | Phi-3-mini (3.8B) vs Phi-3.5-mini (3.8B); latter has stronger instruction following | Phase 1 start          |
| Milvus deployment mode?   | Standalone Docker vs Milvus Lite (embedded); Lite simpler for single-machine        | Phase 2 start          |
| Volunteer list migration? | Keep CSV or move to SQLite table for atomic remove operations                       | Phase 1                |
| Givebutter integration?   | Sync volunteer roster from Givebutter API vs manual CSV export                      | Phase 2                |
| Shadow mode duration?     | 1 week minimum recommended; adjust based on email volume                            | Phase 4                |

# **10\. Risks & Mitigations**

| **Risk**                                                      | **Severity** | **Mitigation**                                                                                                |
| ------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------- |
| Phi misclassifies a sponsor email as general; cold reply sent | High         | Confidence floor + shadow mode testing before live send; sponsor_inquiry gets extra weight in prompt examples |
| Milvus KB returns stale content after event details change    | Medium       | Hash-based re-index on KB file changes; KB documents dated and versioned                                      |
| Graph API OAuth token expires mid-campaign                    | Medium       | MSAL token cache with silent refresh; alert to Telegram if refresh fails                                      |
| Telegram bot goes offline; escalation alerts not delivered    | High         | Health check ping every 15 min; fallback to email-to-self if Telegram unreachable                             |
| Volunteer CSV corrupted by concurrent write                   | Low          | Write to temp file then atomic rename; SQLite migration eliminates this in Phase 2                            |
| Phi draft contains hallucinated facts about GiveCamp          | Medium       | Prompt explicitly forbids facts not in KB context; all drafts log KB hits used                                |

# **Appendix A - Glossary**

| **Term**         | **Definition**                                                                                                                  |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| conversationId   | Microsoft Graph API identifier that groups all replies in an email thread under a single ID, regardless of subject line changes |
| Milvus           | Open-source vector database used for storing and querying document embeddings by cosine similarity                              |
| Phi              | Microsoft's small language model family; Phi-3-mini or Phi-3.5-mini run locally via Ollama on the operator's GPU                |
| SLM              | Small Language Model - a compact LLM suitable for local inference on consumer GPU hardware                                      |
| all-MiniLM-L6-v2 | Sentence-transformers embedding model; 384-dimensional vectors; runs on CPU; no GPU required                                    |
| KB               | Knowledge Base - curated markdown documents covering GiveCamp FAQs, used as retrieval context                                   |
| MSAL             | Microsoft Authentication Library - handles OAuth 2.0 token acquisition and refresh for Graph API access                         |
| Ollama           | Local LLM serving tool that manages model downloads, GPU memory, and an OpenAI-compatible REST API                              |
| Shadow mode      | Operating mode in which the system classifies and logs decisions but does not send any emails; used for pre-launch validation   |

_- End of Document -_

Seattle GiveCamp | seattlegivecamp.org