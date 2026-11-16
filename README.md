# Mowafag100 — Autonomous Security Surveillance Agent

**An AI agent that watches, decides, and acts on its own.**

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-yellow.svg)](https://ultralytics.com/)

![Dashboard Preview](docs/screenshots/dashboard.png)

## What This Agent Does

Mowafag100 is not a passive CCTV system. It is an **autonomous security agent** that continuously monitors multiple camera feeds, makes decisions about what constitutes a threat, and executes responses—all without waiting for human instruction.

## The Agentic Loop

| Phase | Autonomous Action |
|-------|-------------------|
| **Perceive** | Ingests RTSP streams, runs YOLOv8 detection + ByteTrack tracking across cameras |
| **Decide** | Checks face recognition against authorized employees; evaluates zone intrusion and behavioral anomalies (running/fall/loitering); determines if escalation is warranted |
| **Act** | Sends Telegram alerts with snapshots; logs decisions with full audit trail; **self-reports camera disconnection without being prompted** |
| **Respond** | LLM assistant answers operator queries in natural language about historical events |

## Key Agentic Capabilities

- **Self-Monitoring & Fault Reporting**: The agent detects when a camera feed drops and autonomously alerts the operator via Telegram. No human trigger required.
- **Context-Aware Escalation**: Employee entry is logged silently. Unknown intrusion triggers immediate alert. The agent decides the difference.
- **Multi-Camera Coordination**: ByteTrack prevents duplicate alerts for the same individual across feeds.
- **Behavioral Anomaly Detection**: Running, fall, and loitering are detected and classified by severity.
- **Hot-Reload Configuration**: Agent continues running while settings change—no restart required.
- **Decision Audit Trail**: Every autonomous decision (alert sent, alert suppressed, anomaly escalated, camera offline) is logged with reasoning and confidence, and is viewable in the admin dashboard.
## Demo Video ( English subtitles)

[Watch the demo](https://drive.google.com/file/d/1g4_K1axUY-4Fe7161MvQG1nlDzRFJq6h/view?usp=sharing)

The video demonstrates: intrusion detection → Telegram alert received → **agent autonomously reports camera disconnection**.

## Target Category (Dubai Create AI Agents Championship)

**Best Business AI Agent** — enabling security firms to reduce false alarms, cut response time, and maintain continuous surveillance without constant human monitoring. Designed to reduce false-alarm review time and eliminate the need for continuous human monitoring of camera feeds.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, Tailwind CSS |
| Backend API | FastAPI, JWT, SQLAlchemy |
| AI / CV | YOLOv8, OpenCV, ByteTrack |
| Database | PostgreSQL 15 |
| Cache | Redis |
| Reporting | ReportLab (Arabic/English PDF) |
| Deployment | Docker Compose |

## Quick Start

```bash
git clone https://github.com/Mowafag100/AI-Surveillance-Agent.git
cd AI-Surveillance-Agent
cp .env.example .env
# Add TELEGRAM_BOT_TOKEN, CHAT_ID, DB passwords
docker compose up -d --build
Access at http://localhost:3001. First registered user becomes Superuser.

Security
100% on-premise processing—no video leaves the local network

bcrypt password hashing, JWT-protected API

Employee face encodings are stored server-side only; all report downloads are logged with user ID and timestamp
```
Developed by Mowafag Fawzy

