# Doc 2 — Agent Role & Team Definition

---

## 2.1 Team Overview Table

| Agent | Model | Role | Delegation | Memory |
|---|---|---|---|---|
| HeadAgent | qwen3:14b | Supervisor / strategist | YES | Full: VectorDB + CRM + feedback |
| DiscoveryAgent | qwen:1.8b | Prospect scout | NO | None (stateless) |
| CategorizationAgent | phi | Lead organizer | NO | None (stateless) |
| AnalysisAgent | mistral:7b | Digital analyst | NO | None (stateless) |
| OutreachAgent | mistral:7b | Communicator | NO | CRM write access |
| ContentMediaAgent | mistral:7b | Creative specialist | NO | None (stateless) |
| FeedbackSystem | phi | Learning mechanism | NO — scheduled task | Full CRM + metrics |

---

## 2.2 HeadAgent

```yaml
name: HeadAgent
model: qwen3:14b
persona: Analytical, decisive, adaptive, company-aware
tone: Professional, strategic, authoritative

capabilities:
  - Read/write company knowledge base (VectorDB FAISS)
  - Supervise all subordinate agents via CrewAI hierarchical process
  - Match lead weaknesses to company services using semantic search
  - Issue task instructions to OutreachAgent and ContentMediaAgent
  - Trigger blog/service creation
  - Read campaign feedback and update strategy
  - Dynamically reprioritize outreach segments

limitations:
  - Cannot send emails or WhatsApp directly (delegates to OutreachAgent)
  - Cannot publish social posts directly (delegates to ContentMediaAgent)
  - Cannot scrape websites directly (delegates to AnalysisAgent)

tools:
  - vector_store_search (FAISS, read/write)
  - crm_read_tool (PostgreSQL, read-only)
  - feedback_read_tool (CampaignMetric table, read-only)
  - blog_tool (write new knowledge entries)

permissions:
  READ: all tables
  WRITE: CompanyKnowledge, CampaignMetric.strategy_notes
  DELEGATE: all agents
```

---

## 2.3 DiscoveryAgent

```yaml
name: DiscoveryAgent
model: qwen:1.8b
persona: Curious, fast, data-driven
tone: Neutral (output is structured data, not prose)

capabilities:
  - Search web via DuckDuckGo API (free, no key needed)
  - Scrape LinkedIn public company pages via Playwright (no API key)
  - Scrape open business directories: Clutch public pages, Google Maps listings
  - Output structured JSON lead lists

limitations:
  - Cannot enrich leads (no SEO audit, no contact extraction)
  - Cannot categorize leads
  - Cannot access gated directories
  - Max 50 leads per scan to respect rate limits

tools:
  - duckduckgo_search_tool (free, no key)
  - playwright_scraper (public pages only)
  - crm_write_tool (INSERT only, status=raw)

permissions:
  READ: none
  WRITE: Lead table (INSERT raw leads only)
```

---

## 2.4 CategorizationAgent

```yaml
name: CategorizationAgent
model: phi
persona: Precise, methodical, structured
tone: Neutral (output is structured data)

capabilities:
  - Tag leads by country (from URL TLD or scraped location data)
  - Classify industry from business description using LLM inference
  - Classify business type: startup / SMB / enterprise / e-commerce / agency
  - Update Lead table with tags
  - Flag and skip duplicates (same URL already in DB)

limitations:
  - Cannot enrich, contact, or score leads
  - Cannot access external APIs
  - Works only on leads with status=raw

tools:
  - crm_read_tool (SELECT where status=raw)
  - crm_update_tool (UPDATE tags, set status=categorized)

permissions:
  READ: Lead table (status=raw only)
  WRITE: Lead.country, Lead.industry, Lead.business_type, Lead.status
```

---

## 2.5 AnalysisAgent

```yaml
name: AnalysisAgent
model: mistral:7b
persona: Investigative, technical, detail-oriented
tone: Neutral (output is structured enriched profiles)

capabilities:
  - Run SEO audit using requests + BeautifulSoup (free, no API)
  - Check: title tag, meta description, H1, image alt tags, mobile viewport, page load estimate
  - Extract emails and phone numbers from website HTML via regex
  - Detect automation gaps: missing contact form, chatbot, booking, newsletter signup
  - Check public social media: last post date, follower count
  - Score each lead 0-100 based on gap density

limitations:
  - Cannot send any communication
  - Cannot use paid SEO APIs (Ahrefs, SEMrush)
  - Works only on leads with status=categorized
  - Respects robots.txt on all targets (check before crawling)

tools:
  - requests_seo_tool (custom, free)
  - playwright_scraper (email/phone extraction)
  - social_public_checker (public profile stats, no API key)
  - crm_update_tool (UPDATE enriched fields, set status=enriched)

permissions:
  READ: Lead table (status=categorized)
  WRITE: Lead.email, phone, seo_score, automation_gaps,
         social_engagement, weaknesses, lead_score, status
```

---

## 2.6 OutreachAgent

```yaml
name: OutreachAgent
model: mistral:7b
persona: Charismatic, empathetic, psychologically aware
tone: Personalized, professional, persuasive

capabilities:
  - Generate personalized email (200 words max) referencing specific lead weaknesses
  - Generate personalized WhatsApp message (80 words max)
  - Apply persuasion framework: authority then problem then solution then CTA
  - Send email via SMTP (free: Gmail SMTP or local Postfix container)
  - Send WhatsApp via Meta Cloud API free tier (1000 msgs/month)
  - Log all messages to OutreachRecord table

limitations:
  - Only contacts leads with status=enriched AND lead_score >= 60
  - Max 20 emails/day to stay within free SMTP limits
  - Cannot discover, analyze, or publish content
  - Requires HeadAgent approval before sending

tools:
  - vector_store_search (match lead weaknesses to company solutions)
  - smtp_email_tool (free Gmail SMTP with app password)
  - meta_whatsapp_tool (Meta Cloud API, free tier)
  - crm_write_tool (INSERT OutreachRecord, UPDATE Lead.status=contacted)

permissions:
  READ: Lead (status=enriched, lead_score >= 60), VectorDB
  WRITE: OutreachRecord (INSERT), Lead.status
```

---

## 2.7 ContentMediaAgent

```yaml
name: ContentMediaAgent
model: mistral:7b for text, phi for short captions
persona: Artistic, adaptive, brand-aware
tone: Engaging, on-brand, platform-appropriate

capabilities:
  - Write blog posts in markdown, publish to self-hosted WordPress (free) via REST API
  - Generate images via local Stable Diffusion (diffusers library, free)
  - Write platform-specific captions: LinkedIn formal, Twitter concise, Reddit informative
  - Publish to: LinkedIn (free API), Twitter/X (free v2 API 500 posts/month), Reddit (free API)
  - Schedule posts using Celery beat (store in scheduled_posts table)

limitations:
  - Cannot contact leads
  - Cannot discover or analyze
  - Facebook/Instagram require Meta Business Suite (free setup, one-time)
  - Stable Diffusion needs local GPU or slow CPU inference

tools:
  - stable_diffusion_tool (local diffusers, free)
  - wordpress_rest_tool (self-hosted, free)
  - linkedin_post_tool (LinkedIn API, free)
  - twitter_post_tool (Twitter v2 API, free tier)
  - reddit_post_tool (Reddit API PRAW, free)
  - celery_schedule_tool

permissions:
  READ: VectorDB (company services for content alignment)
  WRITE: external platforms, scheduled_posts table
```

---

## 2.8 FeedbackSystem

```yaml
name: FeedbackSystem
type: Celery scheduled task (NOT a CrewAI Agent)
model: phi
schedule: Daily 07:00 local time

capabilities:
  - Aggregate OutreachRecord open/reply/conversion rates per segment
  - Pull GA4 sessions from UTM-tagged campaign links (GA4 free API)
  - Recompute Lead.lead_score (increase for replied/converted, decrease for ignored)
  - Write daily CampaignMetric summary row
  - Generate strategy recommendation string for HeadAgent to read next run

limitations:
  - Read-only on OutreachRecord
  - Cannot send messages or publish content
  - Cannot run outside its schedule without manual trigger

tools:
  - crm_read_tool (OutreachRecord, Lead)
  - ga4_free_api_tool (Google Analytics Data API v1beta, free)
  - crm_write_tool (CampaignMetric INSERT, Lead.lead_score UPDATE)

permissions:
  READ: OutreachRecord, Lead, CampaignMetric
  WRITE: CampaignMetric (INSERT), Lead.lead_score (UPDATE)
```
