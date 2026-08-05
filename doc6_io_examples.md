# Doc 6 — Input/Output Examples & Conversation Flow

---

## 6.1 Golden Path: Full Pipeline Run

### Trigger
```
POST /run/pipeline
Body: {"industry": "e-commerce", "country": "TN", "limit": 10}
```

---

### Step 1 — DiscoveryAgent Output
```json
{
  "from": "DiscoveryAgent",
  "task_id": "discovery_task",
  "status": "success",
  "payload": {
    "leads": [
      {"name": "TunisShop", "url": "https://tunisshop.tn", "industry": "e-commerce", "source": "duckduckgo"},
      {"name": "CarthagoMall", "url": "https://carthagomall.com", "industry": "e-commerce", "source": "playwright_directory"},
      {"name": "SoukConnect", "url": "https://soukconnect.tn", "industry": "marketplace", "source": "duckduckgo"}
    ],
    "total_found": 10,
    "duplicates_skipped": 2
  }
}
```

---

### Step 2 — CategorizationAgent Output
```json
{
  "from": "CategorizationAgent",
  "task_id": "categorization_task",
  "status": "success",
  "payload": {
    "categorized_count": 10,
    "sample": [
      {"lead_id": "uuid-001", "name": "TunisShop", "country": "TN", "industry": "e-commerce", "business_type": "SMB", "status": "categorized"},
      {"lead_id": "uuid-002", "name": "CarthagoMall", "country": "TN", "industry": "e-commerce", "business_type": "enterprise", "status": "categorized"}
    ]
  }
}
```

---

### Step 3 — AnalysisAgent Output
```json
{
  "from": "AnalysisAgent",
  "task_id": "analysis_task",
  "status": "success",
  "payload": {
    "enriched_count": 10,
    "enriched_profiles": [
      {
        "lead_id": "uuid-001",
        "name": "TunisShop",
        "url": "https://tunisshop.tn",
        "email": "contact@tunisshop.tn",
        "phone": "+21698123456",
        "seo_score": 32,
        "seo_issues": ["Missing meta description", "No H1 tag", "4 images missing alt text"],
        "automation_gaps": ["no chatbot", "no email capture form", "manual order processing"],
        "social_engagement": {"platform": "instagram", "followers": 890, "last_post_days_ago": 45},
        "weaknesses": ["poor SEO", "no automation", "low social presence"],
        "lead_score": 78,
        "status": "enriched"
      }
    ]
  }
}
```

---

### Step 4 — HeadAgent Review Output
```json
{
  "from": "HeadAgent",
  "task_id": "head_review_task",
  "status": "success",
  "payload": {
    "approved_leads_count": 7,
    "outreach_briefs": [
      {
        "lead_id": "uuid-001",
        "company_name": "TunisShop",
        "weakness_summary": "Poor SEO (score 32/100), no chatbot, 45 days without social media activity.",
        "matched_services": [
          {"title": "SEO Optimization Package", "description": "Full on-page SEO audit and fix"},
          {"title": "WhatsApp Chatbot Integration", "description": "Automated customer support chatbot"}
        ],
        "recommended_tone": "empathetic, ROI-focused",
        "channel_priority": "email",
        "fallback_channel": "whatsapp"
      }
    ],
    "content_brief": {
      "topic": "Why Tunisian e-commerce stores are losing customers to poor SEO",
      "target_audience": "SMB store owners in Tunisia",
      "key_points": ["SEO drives 60% of organic traffic", "Chatbots reduce cart abandonment by 30%"],
      "platforms": ["linkedin", "twitter", "reddit"],
      "image_prompt": "Modern Tunisian e-commerce dashboard with analytics charts, clean minimal design, blue and white"
    },
    "skipped_leads_count": 3,
    "skip_reasons": ["lead_score < 60", "no_service_match"]
  }
}
```

---

### Step 5 — OutreachAgent: Generated Email (uuid-001)

**Subject:** TunisShop is leaving money on the table — here's how to fix it

**Body:**
```
Hi TunisShop team,

I came across your store and noticed a few things holding back your growth:

• Your SEO score is 32/100 — meaning most potential customers never find you on Google.
• You have no automated chatbot, so every support question requires manual handling.
• Your last Instagram post was 45 days ago — customers are checking and moving on.

At The Next Level Tech Company, we've helped stores exactly like yours fix all three in under 4 weeks.

Our SEO Optimization Package gets you ranking on the first page.
Our WhatsApp Chatbot handles 80% of customer questions automatically.

Would you be open to a 15-minute call this week?

Reply to this email or WhatsApp us at +216XXXXXXXX.

Best,
[Company Name] AI Marketing Team
```

**OutreachRecord entry:**
```json
{
  "lead_id": "uuid-001",
  "channel": "email",
  "to": "contact@tunisshop.tn",
  "subject": "TunisShop is leaving money on the table — here's how to fix it",
  "sent_at": "2025-01-15T10:45:00Z",
  "opened": false,
  "replied": false,
  "converted": false
}
```

---

### Step 6 — ContentMediaAgent Output

**Blog post published to WordPress:**
```json
{
  "post_id": 142,
  "url": "https://nextleveltech.tn/blog/tunisian-ecommerce-seo-guide",
  "title": "Why Tunisian e-commerce stores are losing customers to poor SEO",
  "word_count": 620
}
```

**Social posts scheduled:**
```json
[
  {"platform": "linkedin", "scheduled_at": "2025-01-15T14:00:00Z", "status": "scheduled"},
  {"platform": "twitter", "scheduled_at": "2025-01-15T14:05:00Z", "status": "scheduled"},
  {"platform": "reddit", "subreddit": "Tunisia", "scheduled_at": "2025-01-15T14:10:00Z", "status": "scheduled"}
]
```

**Image generated:**
```json
{"path": "static/images/a3f7c1b2-....png", "prompt": "Modern Tunisian e-commerce dashboard..."}
```

---

## 6.2 Edge Case: Email Bounces, WhatsApp Fallback

```
OutreachAgent sends email to bounced@invalid.tn
SMTP returns: SMTPRecipientsRefused (550)

→ OutreachRecord.status = "bounced"
→ Check: does lead have phone number?
  YES → send WhatsApp message instead
  → OutreachRecord.channel = "whatsapp_fallback"

  NO → OutreachRecord.status = "unreachable"
     → Lead.status = "unreachable"
     → Do not retry for 30 days
```

---

## 6.3 Edge Case: No Matching Company Service

```
AnalysisAgent enriches a lead: "AgroTech Tunisia" (agriculture sector)
HeadAgent searches VectorDB for matching services

→ VectorDB returns 0 results with score > 0.5
→ HeadAgent decision:
  - Skip outreach for this lead
  - Log Lead.status_notes = "no_service_match"
  - Trigger ContentMediaAgent with general brand post (no lead-specific outreach)
  - Alert operator: "Consider adding an AgriTech service to company KB"
```

---

## 6.4 FeedbackSystem Daily Report (Output)

```json
{
  "date": "2025-01-15",
  "total_sent": 20,
  "open_rate": 0.35,
  "reply_rate": 0.12,
  "conversion_rate": 0.05,
  "top_segment": {"industry": "e-commerce", "country": "TN", "conversion_rate": 0.10},
  "worst_segment": {"industry": "retail", "country": "DZ", "conversion_rate": 0.01},
  "strategy_recommendation": "Increase outreach to Tunisian e-commerce SMBs. Reduce threshold from 60 to 50 for this segment. Consider updating retail DZ messaging — current tone not resonating.",
  "lead_scores_updated": 20
}
```

---

## 6.5 Manual Trigger Examples (API)

```bash
# Run full pipeline
curl -X POST http://localhost:8000/run/pipeline \
  -H "Content-Type: application/json" \
  -d '{"industry": "retail", "country": "DZ", "limit": 20}'

# Add a new service to VectorDB
curl -X POST http://localhost:8000/company_db \
  -H "Content-Type: application/json" \
  -d '{"type": "service", "title": "Mobile App Development", "content": "We build custom mobile apps for iOS and Android..."}'

# Check latest feedback
curl http://localhost:8000/feedback/latest

# Get all enriched leads
curl "http://localhost:8000/leads?status=enriched&min_score=60"
```
