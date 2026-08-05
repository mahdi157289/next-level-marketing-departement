# Doc 1 — System / Product Requirements Document (PRD)

---

## 1.1 Product Name

**NextLevel AI Marketing Department**

---

## 1.2 Purpose

Automate the full B2B marketing pipeline — from prospect discovery to outreach to content publishing — using a coordinated multi-agent AI system. The system replaces manual lead research, manual outreach writing, and manual social media posting with autonomous agents supervised by a central AI strategist.

**Constraint: Every tool, model, API, and service used must be free or open-source. No paid subscriptions.**

---

## 1.3 Use Cases and User Stories

| ID | As a… | I want to… | So that… |
|---|---|---|---|
| UC-01 | Marketing manager | Trigger a discovery scan for startups in a target industry | I get a fresh lead list without manual research |
| UC-02 | Marketing manager | Have leads automatically categorized by country and industry | I don't spend time organizing spreadsheets |
| UC-03 | Marketing manager | Receive enriched profiles with SEO scores and contact info | I know which leads are worth pursuing |
| UC-04 | Marketing manager | Get personalized outreach emails and WhatsApp messages drafted and sent automatically | I can run outreach campaigns at scale |
| UC-05 | Marketing manager | Have blog posts and social media updates created and published automatically | Company content is always active |
| UC-06 | Marketing manager | See campaign performance metrics and strategy updates from the AI | The system improves itself over time |
| UC-07 | Business owner | Add a new company service to the knowledge base | All future outreach reflects updated offerings |
| UC-08 | Developer | Run the entire system in Docker containers on a local machine | No cloud costs, full control |

---

## 1.4 Success Criteria

| Metric | Target |
|---|---|
| Leads discovered per scan | ≥ 20 per trigger |
| Enrichment accuracy (correct email extraction) | ≥ 85% |
| Outreach message personalization | Each message references at least 2 specific weaknesses of the target |
| Pipeline end-to-end execution time | < 10 minutes for 10 leads |
| System cost | $0 (all free/open-source) |
| Uptime (after deployment) | ≥ 95% |
| Feedback loop cycle | Daily |

---

## 1.5 Constraints

- **No paid APIs**: SerpAPI → DuckDuckGo. Twilio → Meta WhatsApp Cloud API free tier. SendGrid → local SMTP (Postfix or Gmail SMTP). DALL·E → local Stable Diffusion. Hootsuite → direct platform free APIs. Mailchimp → Listmonk (self-hosted). Weaviate Cloud → local FAISS. Crunchbase → open directory scraping.
- **Local LLM inference**: All models run via Ollama on local hardware. Minimum 16 GB RAM, 8 GB VRAM recommended.
- **No GPU required for light agents**: Phi-2 and Qwen-1.8B run on CPU.
- **Data privacy**: No lead data leaves the local environment. All storage is local PostgreSQL + FAISS.
- **Robots.txt compliance**: All scrapers must check and respect `robots.txt` before crawling.
- **Rate limiting**: All external API calls must respect rate limits. Max 1 req/sec to any single domain.

---

## 1.6 Out of Scope (Phase 1)

- Real-time chat interface for leads
- Multi-tenant support (single company only)
- Voice or video outreach
- Paid ad campaign management
- Mobile app

---

## 1.7 Assumptions

- The company has at least 5 services/solutions documented and ready to load into the vector DB.
- The operator has a machine with at least 16 GB RAM to run Qwen3-14B via Ollama.
- Gmail SMTP or a local Postfix container is available for email sending.
- Meta WhatsApp Cloud API free tier is registered (1,000 free messages/month).
