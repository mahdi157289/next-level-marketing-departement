# Doc 4 — Communication & Coordination Protocol

---

## 4.1 Message Format

All inter-agent messages passed through CrewAI context follow this JSON envelope:

```json
{
  "from": "AnalysisAgent",
  "to": "HeadAgent",
  "task_id": "analysis_task",
  "timestamp": "2025-01-15T09:32:00Z",
  "status": "success",
  "payload": {
    "enriched_leads": [
      {
        "lead_id": "uuid-...",
        "name": "Acme Store",
        "url": "https://acmestore.tn",
        "email": "contact@acmestore.tn",
        "seo_score": 34,
        "automation_gaps": ["no chatbot", "no email capture"],
        "weaknesses": ["poor SEO", "no CRM"],
        "lead_score": 72
      }
    ]
  },
  "error": null
}
```

**Required fields for every message:**

| Field | Type | Description |
|---|---|---|
| from | string | Sender agent name |
| to | string | Receiver agent name |
| task_id | string | CrewAI task identifier |
| timestamp | ISO 8601 | UTC time of message creation |
| status | enum | success / partial / failed |
| payload | object | Task-specific data (see per-task schema) |
| error | string or null | Error message if status=failed |

---

## 4.2 Handoff Ritual

**Standard handoff sequence:**

```
1. Upstream agent completes task
2. Agent writes output to PostgreSQL (primary store)
3. Agent returns structured JSON summary to CrewAI task result
4. CrewAI passes task result as `context` to downstream task
5. Downstream agent reads from both CrewAI context AND PostgreSQL
   (PostgreSQL is source of truth; CrewAI context is confirmation)
6. Downstream agent logs its own start timestamp to task_log table
```

**Handoff validation rule:**
Before starting, every agent runs:
```python
def validate_upstream(expected_status: str, table: str, min_count: int):
    count = db.query(f"SELECT COUNT(*) FROM {table} WHERE status='{expected_status}'")
    assert count >= min_count, f"Upstream not ready: {count} records, expected >= {min_count}"
```
If validation fails → agent raises `UpstreamNotReadyError` → CrewAI retries after 30s (max 3 retries).

---

## 4.3 Shared Memory / State

| Data Store | What lives there | Who reads | Who writes |
|---|---|---|---|
| PostgreSQL Lead table | All lead data, status progression | All agents | Discovery, Categorization, Analysis, Outreach, Feedback |
| PostgreSQL OutreachRecord | Sent messages, open/reply/convert | FeedbackSystem | OutreachAgent |
| PostgreSQL CampaignMetric | Daily performance metrics | HeadAgent | FeedbackSystem |
| FAISS VectorDB | Company services, blogs, embeddings | HeadAgent, OutreachAgent | HeadAgent |
| Celery Redis | Scheduled tasks queue | Celery worker | ContentMediaAgent, FeedbackSystem |
| task_log table | Agent start/end times, task status | Monitoring (Grafana) | All agents |

**State progression (Lead.status FSM):**
```
raw → categorized → enriched → contacted → converted
                                         → unreachable
                                         → low_priority
```
No agent may skip a status step. No agent may move a lead backwards.

---

## 4.4 Context Passing Between Agents

CrewAI passes task outputs via the `context` parameter. Each downstream task receives the full output string of its upstream tasks. Agents must parse this using the standard envelope format.

**Example: HeadAgent receiving AnalysisAgent output**

```python
# In head_review_task definition:
context=[analysis_task]

# HeadAgent receives as context:
"""
Task: analysis_task | Status: success
Enriched 12 leads. Top leads by score:
[{"lead_id": "abc", "lead_score": 85, "weaknesses": [...], ...}]
Full data available in PostgreSQL leads table (status=enriched).
"""

# HeadAgent action:
1. Parse lead_ids from context
2. Query PostgreSQL for full enriched profiles
3. Query FAISS for matching services per lead
4. Build outreach_brief JSON
5. Return as task output for OutreachAgent and ContentMediaAgent
```

---

## 4.5 Conflict Resolution

**Rule 1 — PostgreSQL wins over LLM memory.**
If an agent's LLM output contradicts data in PostgreSQL (e.g., claims a lead has no email when the DB has one), the DB value is used. LLM output is for generation only, not for overriding stored facts.

**Rule 2 — HeadAgent has final authority.**
If OutreachAgent and ContentMediaAgent receive conflicting briefs (should not happen, but possible in retries), HeadAgent's most recent task output is the authoritative source. Both agents re-request from HeadAgent.

**Rule 3 — Failed task does not block parallel sibling.**
If outreach_task fails (SMTP down), content_task continues independently. Both log their status to task_log. Pipeline resumes outreach_task on next cycle using cached head_review_task output (stored in PostgreSQL).

**Rule 4 — Duplicate prevention.**
Before OutreachAgent sends any message, it checks:
```sql
SELECT COUNT(*) FROM outreach_records
WHERE lead_id = :lead_id AND sent_at > NOW() - INTERVAL '30 days'
```
If count > 0, skip this lead. Do not re-contact within 30 days.

---

## 4.6 Logging Protocol

Every agent logs to `task_log` table at start and end:

```sql
CREATE TABLE task_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name VARCHAR(64),
  task_id VARCHAR(128),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  status VARCHAR(16),   -- running / success / failed / retrying
  records_processed INT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Grafana alert rule:**
If any task_log row has `status='failed'` and `finished_at > NOW() - INTERVAL '1 hour'` → send alert to operator log file.
