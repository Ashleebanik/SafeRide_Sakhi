# SafeRide Sakhi 🛡️
### AI-Powered Night-Travel Safety Agent System for Women

> **Challenge build — 10 Nov 2026 · @Ashlee**  
> All trip data is **synthetic / simulated**. No real personal data is used anywhere.

---

## Overview

SafeRide Sakhi is a multi-agent, AI-powered safety system that anticipates when a woman needs a night-time ride, books it with a verified woman chauffeur, monitors the whole journey, detects warning signs early, and acts through a graded escalation ladder — always with a human in the loop for serious cases.

```
Signal → Agent Pipeline → Risk Score → Context Assessment → Escalation → Human Review
```

---

## Architecture

### Seven Agents

| # | Agent | Role | LLM |
|---|-------|------|-----|
| 1 | **Context & Anticipation** | Reads shift rosters / calendars; suggests ride proactively | Rule-based |
| 2 | **Chauffeur Verification & Matching** | ID, police verification, face-match, proximity | Rule-based |
| 3 | **Live Trip Monitoring** | GPS trace vs planned route, stops, silence | Rule-based |
| 4 | **Risk & Anomaly Detection** | Scores all signals 0–1, sets risk level | **IBM Granite 4** |
| 5 | **Context & Impact Assessment** | Area type, lighting, help points, severity | **Google Gemini** |
| 6 | **Alert & Escalation** | Nudge → Alert → Emergency ladder, message drafting | **Groq (Llama 3)** |
| 7 | **Response & Safe-Arrival** | Nearest safe stop, arrival confirmation, outcome log | Rule-based |

### Supervisor / Orchestrator

A single `orchestrator.py` supervisor holds the shared `TripState` and passes it through agents in sequence. Agents never communicate directly — only through the supervisor.

```
Supervisor
  ├─ Agent 1  (pre-trip)
  ├─ Agent 2  (pre-trip)
  ├─ Agent 3  (live, each GPS cycle)
  ├─ Agent 4  (risk score)
  ├─ Agent 5  (context weight)
  ├─ Agent 6  (escalation — triggered by risk ≥ 0.35)
  └─ Agent 7  (closure)
```

### Risk Ladder

| Score | Level | Action |
|-------|-------|--------|
| < 0.35 | **Safe** | No action |
| 0.35–0.59 | **Nudge** | Ask rider "are you OK?" |
| 0.60–0.79 | **Alert** | Notify trusted contacts; human review |
| ≥ 0.80 | **Emergency** | Control room alert; human decides on 112 |

> **POLICY:** No LLM output alone can trigger emergency services. A human must review every Alert and Emergency case.

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 |
| Agent framework | Custom ReAct loop (capped at 6 iterations) |
| Risk reasoning LLM | IBM Granite 4 via watsonx.ai |
| Context assessment LLM | Google Gemini 1.5 Flash |
| Alert drafting LLM | Groq Llama3-70B |
| Guardrails | NeMo Guardrails |
| Vector memory | ChromaDB |
| Dashboard | Streamlit + Folium |
| Observability | structlog → JSONL |
| Data | Synthetic only (Faker, random seed) |

---

## Project Structure

```
saferide_sakhi/
├── config.py              # All settings from .env
├── models.py              # Pydantic v2 domain models
├── logger.py              # Structured JSONL logger
├── orchestrator.py        # Supervisor agent
├── agents/
│   ├── agent1_anticipation.py
│   ├── agent2_verification.py
│   ├── agent3_monitoring.py
│   ├── agent4_risk.py          # IBM Granite 4
│   ├── agent5_impact.py        # Gemini
│   ├── agent6_escalation.py    # Groq
│   └── agent7_safe_arrival.py
├── mcp_tools/
│   └── tools.py           # Route deviation, stops, silence, help points, alerts
├── data/
│   ├── generate.py        # Synthetic data generator
│   └── synthetic/         # Generated JSON files (gitignored)
├── dashboard/
│   └── app.py             # Streamlit control-room dashboard
├── tests/
│   └── test_agents.py     # pytest suite
├── prompts/               # Versioned prompt templates
├── logs/                  # JSONL agent logs
├── requirements.txt
└── .env.example
```

---

## Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r saferide_sakhi/requirements.txt
```

### 2. Configure environment

```bash
copy saferide_sakhi\.env.example saferide_sakhi\.env
# Edit .env and fill in your API keys
```

### 3. Generate synthetic data

```bash
python -m saferide_sakhi.data.generate
```

### 4. Run tests

```bash
pytest saferide_sakhi/tests/ -v
```

### 5. Launch dashboard

```bash
streamlit run saferide_sakhi/dashboard/app.py
```

---

## Evaluation

| Measure | How tested |
|---------|-----------|
| **Accuracy** | Share of injected deviations & silences detected; false-alarm rate |
| **Speed** | Time from signal to nudge; time to control-room alert |
| **Cost** | Tokens & estimated cost per trip (logged per LLM call) |
| **Reliability** | Rate of invalid outputs caught by rule-based fallback |

---

## Guardrails & Governance

- **NeMo Guardrails**: protects against prompt injection via driver notes or chat
- **Schema validation**: every LLM output is validated against a fixed Pydantic schema; invalid outputs fall back to rule-based scoring
- **Human in the loop**: Alert and Emergency steps are `dry_run=True` unless a human explicitly approves
- **Prompt versioning**: every prompt includes a `prompt_version` field logged with each decision
- **Audit log**: all agent steps logged to `logs/saferide_sakhi.jsonl` (input, tool, output, latency, decision)
- **Kill switch**: set `human_override=True` on any `TripState` via the dashboard to freeze escalation
- **Data deletion**: `TRIP_DATA_RETENTION_DAYS` config controls automatic log rotation

## Responsible AI

- Rider controls who sees her location (`consent_location_sharing`)
- Recording is off by default (`consent_recording=False`)
- No real personal data in the challenge build
- Area-type classification uses only public OSM bounding boxes — no community or demographic profiling

---

## IBM Bob Modes Used

| Bob Mode | Used For |
|----------|---------|
| **Plan** | Architecture design, agent breakdown, data flow |
| **Ask** | API questions (watsonx, Gemini, Groq), NeMo Guardrails integration |
| **Agent** | Building and testing all code, generating synthetic data |

---

*SafeRide Sakhi · Challenge Build · IBM Bob + IBM Granite + Gemini + Groq · Synthetic data only*
