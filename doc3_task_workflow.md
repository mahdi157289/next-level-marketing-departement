# Doc 3 — Task & Workflow Decomposition

---

## 3.1 Task List

| Task ID | Task Name | Agent | Input | Expected Output |
|---|---|---|---|---|
| T-01 | web_discovery | DiscoveryAgent | industry keyword, country | JSON list of raw leads |
| T-02 | categorize_leads | CategorizationAgent | raw leads from CRM | Tagged leads in CRM (status=categorized) |
| T-03 | enrich_leads | AnalysisAgent | categorized leads from CRM | Enriched profiles in CRM (status=enriched) |
| T-04 | head_review | HeadAgent | enriched profiles + company VectorDB | Approved lead list + outreach brief per lead |
| T-05 | send_outreach | OutreachAgent | outreach brief from HeadAgent | Sent messages logged in OutreachRecord |
| T-06 | create_content | ContentMediaAgent | content brief from HeadAgent | Published blog post + social media posts |
| T-07 | collect_feedback | FeedbackSystem | OutreachRecord + GA4 | Updated lead scores + CampaignMetric row |
| T-08 | strategy_update | HeadAgent | latest CampaignMetric | Updated strategy notes in DB |

---

## 3.2 Workflow Sequence

```
TRIGGER: POST /run/pipeline  (or cron daily)
    |
    v
[T-01] DiscoveryAgent
  Input:  { "industry": "e-commerce", "country": "TN", "limit": 50 }
  Output: raw leads written to PostgreSQL Lead table
  Test:   assert Lead count increased, status="raw"
    |
    v
[T-02] CategorizationAgent
  Input:  SELECT * FROM leads WHERE status='raw'
  Output: leads updated with country/industry/business_type tags
  Test:   assert all raw leads now status="categorized", no null tags
    |
    v
[T-03] AnalysisAgent
  Input:  SELECT * FROM leads WHERE status='categorized'
  Output: leads updated with seo_score, email, weaknesses, lead_score
  Test:   assert enriched fields populated, status="enriched"
    |
    v
[T-04] HeadAgent (review + match)
  Input:  enriched leads + VectorDB semantic search
  Output: approved_leads list + outreach_brief per lead (JSON)
          content_brief for ContentMediaAgent (JSON)
  Test:   assert each approved lead has matched_services[] populated
    |
    +---------------------------+
    |                           |
    v                           v
[T-05] OutreachAgent      [T-06] ContentMediaAgent
  Parallel execution        Parallel execution
  Input: outreach_briefs    Input: content_brief
  Output: emails/WA sent    Output: blog + social posts published
  Test: OutreachRecord rows  Test: HTTP 200 from CMS + social APIs
    |                           |
    +---------------------------+
    |
    v (runs next day via Celery beat)
[T-07] FeedbackSystem
  Input:  OutreachRecord (last 7 days) + GA4 API
  Output: CampaignMetric row, lead scores updated
  Test:   assert CampaignMetric row exists for today
    |
    v
[T-08] HeadAgent (strategy update)
  Input:  latest CampaignMetric
  Output: strategy_notes updated in CampaignMetric table
  Test:   assert strategy_notes not null/empty
```

---

## 3.3 Decision Branching

```
After T-03 (AnalysisAgent output):
  IF lead_score >= 60:
    → HeadAgent approves → T-05 (outreach)
  IF lead_score < 60:
    → Lead stays status="enriched", flagged as low_priority
    → HeadAgent may assign to content targeting (brand awareness only)

After T-04 (HeadAgent match):
  IF matched_services is empty (no company service fits lead weaknesses):
    → HeadAgent skips outreach for that lead
    → Logs: "no_match" in Lead.status_notes
    → Triggers T-06 (content) with a general brand post instead

After T-05 (OutreachAgent):
  IF email bounces (SMTP 550 error):
    → Retry WhatsApp channel if phone number available
    → Log OutreachRecord.channel="whatsapp_fallback"
  IF WhatsApp also fails:
    → Log status="unreachable", do not retry for 30 days

After T-07 (FeedbackSystem):
  IF conversion_rate < 5% for a segment:
    → HeadAgent receives flag: "low_performing_segment:{segment}"
    → HeadAgent updates outreach tone/offer for that segment next cycle
  IF conversion_rate >= 20% for a segment:
    → HeadAgent increases lead_score threshold from 60 → 50 for that segment
    → More leads qualify for outreach in next cycle
```

---

## 3.4 Parallel vs Sequential

| Stage | Mode | Reason |
|---|---|---|
| T-01 → T-02 → T-03 → T-04 | Sequential | Each stage depends on previous output |
| T-05 and T-06 | Parallel | Outreach and content creation are independent |
| T-07 | Async / scheduled | Runs on Celery beat, not blocking pipeline |
| T-08 | Sequential after T-07 | Needs FeedbackSystem output |

---

## 3.5 CrewAI Task YAML Reference

```yaml
# workflows/tasks.yaml

discovery_task:
  description: >
    Search the web and public directories for startups and companies
    in the {industry} sector in {country}. Output a JSON list of raw leads
    with fields: name, url, country, industry, source.
  expected_output: JSON array of lead objects, minimum 10 items.
  agent: discovery_agent

categorization_task:
  description: >
    Read all leads with status=raw from the CRM.
    Tag each with country, industry, and business_type.
    Flag duplicates. Update status to categorized.
  expected_output: Confirmation string with count of categorized leads.
  agent: categorization_agent
  context: [discovery_task]

analysis_task:
  description: >
    For each lead with status=categorized, visit the website,
    run SEO checks, extract contact info, detect automation gaps,
    compute lead_score 0-100. Update CRM. Set status=enriched.
  expected_output: JSON array of enriched profiles.
  agent: analysis_agent
  context: [categorization_task]

head_review_task:
  description: >
    Review all enriched leads. Use VectorDB to match each lead's weaknesses
    to company services. Approve leads with lead_score >= 60.
    For each approved lead, write an outreach_brief with: lead_id, weakness_summary,
    matched_services[], recommended_tone, channel_priority (email/whatsapp).
    Write a content_brief for ContentMediaAgent.
  expected_output: JSON object with approved_leads[] and content_brief.
  agent: head_agent
  context: [analysis_task]

outreach_task:
  description: >
    For each lead in approved_leads, generate a personalized message
    referencing weakness_summary and matched_services.
    Send via channel_priority. Log to OutreachRecord.
  expected_output: JSON array of OutreachRecord objects (lead_id, channel, sent_at).
  agent: outreach_agent
  context: [head_review_task]

content_task:
  description: >
    Using content_brief from HeadAgent, write one blog post and
    three social media captions (LinkedIn, Twitter, Reddit).
    Generate one image via Stable Diffusion.
    Publish blog to WordPress. Schedule social posts via Celery.
  expected_output: URLs of published blog post and confirmation of scheduled social posts.
  agent: content_media_agent
  context: [head_review_task]
```
