# ARGUS

> **Autonomous Risk Governance and Unified Surveillance**  
> AI-native situational awareness and predictive crowd safety platform for large-scale hospitality venues

---

## What is ARGUS?

Large venues — stadiums, concert halls, festival grounds — generate thousands of concurrent data streams: CCTV feeds, environmental sensors, access control events, crowd flow readings, POS transactions. Human operators cannot monitor all of them simultaneously. Incidents happen not because the data wasn't there, but because no one was watching the right stream at the right moment.

ARGUS is the layer between raw sensor infrastructure and the humans responsible for keeping a venue safe. It fuses all incoming data into a single continuously-updated probabilistic venue state model, detects dangerous crowd conditions before they become incidents, and surfaces ranked actionable signals to operators through a live digital twin map and a natural-language assistant.

The centrepiece is predictive egress forecasting: ARGUS detects a crowd building toward Gate B and tells the duty manager — four minutes before it becomes critical — exactly which exits to open and where to deploy staff.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Sensor Layer                             │
│  CCTV · Env IoT · Access Control · Crowd Flow · POS · External │
└───────────────────────────┬─────────────────────────────────────┘
                            │ raw events
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              Go — Event Broker + Stream Normaliser              │
│         Kafka topics · timestamp alignment · validation         │
└──────────┬──────────────────────────────────┬───────────────────┘
           │ normalised streams               │
           ▼                                  ▼
┌──────────────────────────┐    ┌─────────────────────────────────┐
│  Go — Venue State Graph  │◀───│     Go — Signal Ranker          │
│  Redis · Bayesian belief │    │  Dedup · severity · suppress    │
│  propagation · 2Hz update│    └────────────────┬────────────────┘
└──────────┬───────────────┘                     │
           │ zone snapshots (500ms)               │ top-7 alerts
           ▼                                      │
┌─────────────────────────────────────────────────┘
│              Python — ML Inference Services
│
│  argus-cv        (port 8001)  YOLOv8n crowd density
│  argus-anomaly   (port 8002)  Panic · crush · counter-flow
│  argus-forecast  (port 8003)  Per-exit egress forecasting
│
└────────────────────────┬────────────────────────────────────────
                         │ inference results → Redis
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Go — API + Transport Layer                    │
│                                                                 │
│  argus-api  (8080)   REST API (Gin)                             │
│  argus-ws   (8081)   WebSocket — 2Hz twin updates + alert push  │
│  argus-nlp  (8082)   NLP proxy → Python operator assistant      │
└──────────┬──────────────────────────────┬───────────────────────┘
           │ REST + WebSocket              │ streaming NLP
           ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      React Frontend                             │
│                                                                 │
│  Digital twin map · Alert queue · Egress forecast panel        │
│  Operator assistant chat · Live metric cards                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
Argus/
├── argus-go/                        # P1 — Go backend services
│   ├── cmd/
│   │   ├── argus-api/               # REST API server (Gin)
│   │   │   └── main.go
│   │   ├── argus-ws/                # WebSocket server
│   │   │   └── main.go
│   │   ├── argus-updater/           # State update loop (calls Python every 500ms)
│   │   │   └── main.go
│   │   └── argus-demo/              # Scripted scenario engine
│   │       └── main.go
│   ├── internal/
│   │   ├── broker/                  # Kafka producer/consumer wrappers
│   │   ├── graph/                   # Venue state graph + Bayesian propagation
│   │   ├── ranker/                  # Signal deduplication + severity scoring
│   │   ├── normaliser/              # Stream timestamp alignment
│   │   └── simulator/               # Synthetic sensor data generator
│   ├── pkg/
│   │   └── schema/                  # Shared Go types (mirrors contracts/)
│   ├── scenarios/
│   │   └── egress_demo.yaml         # Scripted 8-minute post-concert egress demo
│   ├── go.mod
│   ├── go.sum
│   ├── Makefile
│   └── Dockerfile
│
├── argus-ml/                        # P2 — Python ML inference services
│   ├── argus-cv/                    # Crowd density via YOLOv8n
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── schemas.py
│   │   │   ├── inference.py
│   │   │   ├── zone_mapper.py
│   │   │   └── preprocess.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── argus-anomaly/               # Behavioural anomaly detection
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── schemas.py
│   │   │   ├── detectors/
│   │   │   │   ├── panic.py
│   │   │   │   ├── crush.py
│   │   │   │   └── counter_flow.py
│   │   │   └── utils.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── argus-forecast/              # Egress congestion forecasting
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── schemas.py
│   │   │   ├── model.py
│   │   │   ├── features.py
│   │   │   └── cache.py
│   │   ├── models/
│   │   │   └── egress_xgb_v1.pkl
│   │   ├── training/
│   │   │   ├── train.py
│   │   │   ├── evaluate.py
│   │   │   └── data/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── data/
│       ├── raw/                     # ShanghaiTech, UCSD datasets (gitignored)
│       └── synthetic/               # Simulator replay frames
│
├── argus-nlp/                       # P3 — Operator assistant service
│   ├── app/
│   │   ├── main.py                  # FastAPI NLP service
│   │   ├── schemas.py               # VenueContext + query models
│   │   ├── prompt.py                # System prompt + context injection template
│   │   ├── router.py                # Query type classifier
│   │   └── history.py               # History endpoint client
│   ├── eval/
│   │   ├── queries.yaml             # 50-query evaluation set
│   │   └── run_eval.py              # Accuracy + latency evaluation harness
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── argus-frontend/                  # P4 — React dashboard
│   ├── src/
│   │   ├── components/
│   │   │   ├── TwinMap/             # Digital twin SVG floor plan + overlays
│   │   │   ├── AlertQueue/          # Ranked alert panel
│   │   │   ├── EgressPanel/         # Per-gate forecast bars
│   │   │   ├── OperatorAssistant/   # NLP chat interface
│   │   │   ├── ZoneDrillDown/       # Zone detail sidebar
│   │   │   └── Header/              # Live metric cards + connection status
│   │   ├── hooks/
│   │   │   ├── useVenueSocket.ts    # WebSocket connection + reconnect logic
│   │   │   └── useZoneHistory.ts    # REST history fetch
│   │   ├── services/
│   │   │   └── api.ts               # REST API client
│   │   ├── store/
│   │   │   └── venueStore.ts        # Zustand global state
│   │   ├── types/
│   │   │   └── index.ts             # TypeScript interfaces (mirrors contracts/)
│   │   └── assets/
│   │       └── venue_floorplan.svg  # Stadium floor plan (15 named zones)
│   ├── public/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── Dockerfile
│
├── contracts/                       # Shared interface definitions (read by all teams)
│   ├── README.md                    # Kafka topics, Redis keys, HTTP schemas — law
│   └── schemas.py                   # Pydantic types (Python reference)
│
├── docker-compose.yml               # Boots the entire system with one command
├── Makefile                         # Convenience targets: run, test, demo, build
├── .env.example                     # All environment variables with defaults
└── README.md                        # This file
```

---

## Services

| Service | Language | Port | Owner |
|---|---|---|---|
| `argus-api` | Go | 8080 | P1 |
| `argus-ws` | Go | 8081 | P1 |
| `argus-nlp-proxy` | Go | 8082 | P1 |
| `argus-cv` | Python | 8001 | P2 |
| `argus-anomaly` | Python | 8002 | P2 |
| `argus-forecast` | Python | 8003 | P2 |
| `argus-nlp` | Python | 8004 | P3 |
| `argus-frontend` | React | 5173 | P4 |
| `redis` | — | 6379 | — |
| `kafka` | — | 9092 | — |
| `ollama` | — | 11434 | P3 |

---

## Quick Start

### Prerequisites

- Docker and Docker Compose v2
- 16 GB RAM recommended (8 GB minimum — Ollama is hungry)
- GPU optional but recommended for `argus-cv`

### Boot the full system

```bash
git clone https://github.com/your-team/argus.git
cd Argus

# Copy environment config
cp .env.example .env

# Pull Ollama model (one-time, ~4GB download)
docker compose run ollama ollama pull mistral:7b-instruct

# Start everything
docker compose up --build
```

The system is ready when all health checks pass:

```bash
make health
# argus-api       → ok
# argus-cv        → ok (model loaded)
# argus-anomaly   → ok
# argus-forecast  → ok (model loaded)
# argus-nlp       → ok (model loaded)
# argus-frontend  → ok
```

Open the dashboard at **http://localhost:5173**

### Run the demo scenario

```bash
# Start the scripted 8-minute post-concert egress scenario
make demo

# Or run it manually
docker compose exec argus-go ./argus-demo --scenario scenarios/egress_demo.yaml
```

The demo scenario timeline:
- `t=0:00` — Normal venue state, 48,000 occupants post-match
- `t=2:00` — North concourse crowd begins moving toward exits
- `t=4:00` — Gate B density crosses WARNING threshold
- `t=5:30` — Anomaly detector fires PANIC signature
- `t=6:00` — CRITICAL alert fires: "Gate B: 91% probability critical in 4.8 min"
- `t=6:10` — Action banner: "Open auxiliary exits C2 and C3"
- `t=7:00` — Density peaks, begins clearing
- `t=8:00` — Scenario ends

---

## Component Details

### Go Backend (`argus-go`)

Four binaries, each with a single responsibility:

**`argus-api`** — REST API server built with Gin. Exposes venue state, zone data, alert queue, and history endpoints. Reads exclusively from Redis — never touches Kafka or Python directly.

**`argus-ws`** — WebSocket hub. Broadcasts `venue_state_update` diffs to all connected clients at 2Hz. Pushes `alert_update` events immediately when the signal ranker produces a new top-7 list.

**`argus-updater`** — The engine room. Consumes normalised sensor events from Kafka, maintains the venue state graph in Redis, calls the three Python ML services every 500ms, runs the Bayesian belief propagation loop, and feeds the signal ranker.

**`argus-demo`** — Scenario replay engine. Reads a `scenario.yaml` timeline and injects synthetic sensor readings directly into Kafka at the correct timesteps. Deterministic — same YAML produces identical output every run.

Key packages: `gin-gonic/gin`, `gorilla/websocket`, `segmentio/kafka-go`, `redis/go-redis/v9`, `rs/zerolog`, `sony/gobreaker`

### Python ML Services (`argus-ml`)

Three stateless FastAPI services called by `argus-updater` every 500ms. Full documentation in [`argus-ml/README.md`](argus-ml/README.md).

**`argus-cv`** — Accepts a base64-encoded camera frame and zone bounding boxes. Runs YOLOv8n person detection, counts detections per zone, returns occupancy counts and density estimates. Target latency: P95 < 300ms on CPU.

**`argus-anomaly`** — Accepts time-series density and flow vector history for a zone. Detects three dangerous crowd signatures: panic (density gradient spike + high velocity), crush precursor (high density + near-zero velocity sustained > 15s), counter-flow (bimodal angular distribution of flow vectors). Pure NumPy — P95 < 20ms.

**`argus-forecast`** — Accepts current gate state and event timing. Returns per-exit congestion probability at T+2, T+5, and T+10 minutes. XGBoost regressor trained on 12,000 simulated egress sequences. P95 < 15ms with 2s response caching.

### NLP Operator Assistant (`argus-nlp`)

FastAPI service wrapping Mistral 7B via Ollama. Every query is answered in the context of live venue state — injected as a structured situation report before the user's question. Query types (STATUS, ALERT, FORECAST, HISTORY, ACTION) are classified and routed to prompt variants tuned for each. Streaming responses via `StreamingResponse`. Target: P95 < 800ms end-to-end.

Example queries the assistant handles:
- *"Which gate will hit critical density first?"*
- *"What triggered the alert in zone 7?"*
- *"What happened in the north concourse in the last five minutes?"*
- *"What should I do right now?"*

### React Frontend (`argus-frontend`)

Single-page operations dashboard built with React, TypeScript, and Tailwind. Dark ops theme — designed to look and feel like a real security operations centre, not a SaaS product.

**Digital twin map** — SVG floor plan of a 15-zone stadium. Zone fills animate between safe (green), elevated (amber), warning (orange), and critical (red) as risk scores update at 2Hz. CRITICAL alerts trigger a pulse animation on the affected zone. Click any zone for a drill-down panel showing occupancy, risk trend sparkline, and contributing factors. Supports zoom and pan.

**Alert queue** — Left sidebar. Up to 7 ranked active alerts, each showing severity badge, zone name, one-line description, and time since fired. Clicking an alert highlights the zone on the twin map.

**Egress forecast panel** — Right sidebar, upper half. One row per exit gate showing T+2/T+5/T+10 congestion probability bars. Most critical gate floats to top. Time-to-critical countdown when T+5 probability exceeds 70%.

**Operator assistant** — Right sidebar, lower half. Text input sending queries to `argus-nlp` via the Go proxy. Streaming token-by-token response display.

**Action banner** — Full-width amber banner that appears automatically when any gate's T+5 forecast crosses 85% critical probability. Shows the specific recommended action with gate names and time estimate. The centrepiece of the demo.

---

## Data Contracts

The `contracts/` directory is the source of truth for all inter-service communication. **Every team member reads this before writing any code that touches another service.**

### Kafka topics

| Topic | Producer | Consumers | Payload |
|---|---|---|---|
| `sensor.raw` | `argus-demo` / simulator | `argus-updater` | `{zone_id, sensor_type, value, timestamp}` |
| `sensor.cv` | `argus-updater` | `argus-updater` | Normalised CV readings |
| `alerts.active` | `argus-updater` | `argus-ws` | Alert queue change events |

### Redis keys

| Key pattern | Type | TTL | Description |
|---|---|---|---|
| `zone:{id}:state` | Hash | none | Current zone risk score, occupancy, anomaly score |
| `zone:{id}:history` | Sorted set | 10 min | Rolling risk score history (score = unix timestamp) |
| `alerts:active` | Sorted set | — | Top-7 alerts sorted by severity score |
| `venue:meta` | Hash | none | Event name, capacity, event end time |

### WebSocket message format

```json
{
  "type": "venue_state_update",
  "ts": 1710540664,
  "zones": [
    { "id": "zone_gate_b_north", "risk": 0.91, "occupancy": 1840, "anomaly": 0.89 }
  ],
  "alerts": [
    { "id": "alert_001", "zone": "zone_gate_b_north", "severity": "CRITICAL",
      "message": "Crowd density 5.1/m² — crush risk elevated", "ts": 1710540601 }
  ]
}
```

---

## Development

### Running a single service locally

```bash
# Go backend
cd argus-go
make run-api          # starts argus-api on :8080
make run-ws           # starts argus-ws on :8081
make run-updater      # starts argus-updater

# Python ML
cd argus-ml/argus-cv
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Frontend
cd argus-frontend
npm install
npm run dev           # starts on :5173
```

### Running tests

```bash
# All services
make test

# Go only
cd argus-go && go test ./...

# Python ML only
cd argus-ml && pytest -v

# Frontend only
cd argus-frontend && npm test

# Integration tests (requires Docker Compose running)
make test-integration
```

### Environment variables

All variables have defaults in `.env.example`. Key overrides:

| Variable | Default | Description |
|---|---|---|
| `KAFKA_BROKERS` | `kafka:9092` | Kafka broker address |
| `REDIS_ADDR` | `redis:6379` | Redis address |
| `ARGUS_CV_URL` | `http://argus-cv:8001` | CV service URL (Go → Python) |
| `ARGUS_ANOMALY_URL` | `http://argus-anomaly:8002` | Anomaly service URL |
| `ARGUS_FORECAST_URL` | `http://argus-forecast:8003` | Forecast service URL |
| `ARGUS_NLP_URL` | `http://argus-nlp:8004` | NLP service URL |
| `OLLAMA_HOST` | `http://ollama:11434` | Ollama LLM host |
| `YOLO_MODEL_VARIANT` | `yolov8n` | YOLOv8 variant |
| `LOG_LEVEL` | `INFO` | Log verbosity |

---

## Evaluation

Benchmark results (Intel i7-12700, Docker, no GPU):

| Service | P50 | P95 | P99 | Throughput |
|---|---|---|---|---|
| `argus-api` REST | 8ms | 22ms | 41ms | 400 req/s |
| `argus-ws` broadcast (50 clients) | — | 95ms | 140ms | — |
| `argus-cv` inference | 198ms | 287ms | 341ms | 4.8 req/s |
| `argus-anomaly` inference | 8ms | 14ms | 19ms | 180 req/s |
| `argus-forecast` inference | 5ms | 11ms | 16ms | 240 req/s |
| `argus-nlp` (streaming P95 first token) | — | 740ms | 890ms | — |

Demo scenario detection performance:

| Metric | ARGUS | Threshold baseline |
|---|---|---|
| Mean time to first signal | 3.2 min | 11.8 min |
| False positive rate (per op-hr) | 5.8 | 18.3 |
| Pre-incident detection < 5 min | 87% | 31% |
| Multi-stream scenario detection | 79% | 14% |

---

## Team

| Role | Name | Module | Responsibility |
|---|---|---|---|
| P1 — Go backend | Ananth Chavan | `argus-go` | Event broker, venue state graph, REST API, WebSocket, demo engine |
| P2 — Python ML | Akshat Kumar Jha | `argus-ml` | CV density, anomaly detection, egress forecasting |
| P3 — NLP + docs | Ishita | `argus-nlp` | Operator assistant, paper, presentation, demo video |
| P4 — Frontend | Anant Shrey | `argus-frontend` | Digital twin map, dashboard, demo recording |

---

## Known Limitations

- `argus-cv` cold-starts take ~15 seconds (YOLOv8 model loading). The Go circuit breaker handles this gracefully — requests during warmup return 503 and are retried automatically.
- The egress forecaster was trained on simulated data. Production deployment would require retraining on real venue egress observations before the accuracy numbers are meaningful.
- `argus-anomaly` counter-flow detection requires at least 10 flow history samples (50 seconds of data) before producing a reliable result. Early readings carry `confidence < 0.5`.
- All Python services are CPU-only by default. A CUDA-capable GPU is required for production deployment with live camera feeds at the latency targets stated above.
- Ollama/Mistral 7B requires ~5 GB VRAM or ~6 GB RAM. On machines below this threshold, NLP response latency will exceed the 800ms target.

---

## License

MIT License. See `LICENSE` for details.

---

*ARGUS · Autonomous Risk Governance and Unified Surveillance*