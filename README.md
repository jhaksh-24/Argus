# ARGUS — ML Inference Services (P2)

> **Part of the ARGUS AI-Native Venue Safety Platform**  
> Autonomous Risk Governance and Unified Surveillance

---

## Overview

This module contains the three Python ML inference services that form the intelligence layer of ARGUS. Every risk score, anomaly flag, and egress forecast surfaced on the operator dashboard originates here.

| Service | Port | Responsibility |
|---|---|---|
| `argus-cv` | `8001` | Crowd density estimation via YOLOv8n |
| `argus-anomaly` | `8002` | Behavioural anomaly detection (panic, crush, counter-flow) |
| `argus-forecast` | `8003` | Per-exit congestion forecasting over a 10-minute horizon |

All three services are called by the Go backend (`argus-updater`) every 500 ms. They are stateless — each request is self-contained.

---

## Architecture

```
Go backend (argus-updater)
        │
        ├── POST /infer/density    ──▶  argus-cv        (YOLOv8n person detection)
        ├── POST /infer/anomaly    ──▶  argus-anomaly    (NumPy signal analysis)
        └── POST /infer/egress     ──▶  argus-forecast   (XGBoost regression)
                │
                └── Results written back to Redis venue state graph
```

Each service is a standalone FastAPI application. They share no state and have no inter-service dependencies. Each runs in its own Docker container.

---

## Repository Structure

```
argus-ml/
├── argus-cv/
│   ├── app/
│   │   ├── main.py              # FastAPI app, /infer/density endpoint
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── inference.py         # YOLOv8 inference pipeline
│   │   ├── zone_mapper.py       # Bounding box → zone assignment logic
│   │   └── preprocess.py        # Frame decoding and resizing
│   ├── tests/
│   │   ├── test_inference.py
│   │   └── test_zone_mapper.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── argus-anomaly/
│   ├── app/
│   │   ├── main.py              # FastAPI app, /infer/anomaly endpoint
│   │   ├── schemas.py
│   │   ├── detectors/
│   │   │   ├── panic.py         # Density gradient + velocity spike detection
│   │   │   ├── crush.py         # High density + near-zero velocity detection
│   │   │   └── counter_flow.py  # Bimodal flow vector detection
│   │   └── utils.py             # Shared signal processing helpers
│   ├── tests/
│   │   ├── test_panic.py
│   │   ├── test_crush.py
│   │   └── test_counter_flow.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── argus-forecast/
│   ├── app/
│   │   ├── main.py              # FastAPI app, /infer/egress endpoint
│   │   ├── schemas.py
│   │   ├── model.py             # XGBoost inference wrapper
│   │   ├── features.py          # Feature engineering from venue state
│   │   └── cache.py             # Response caching layer (2s TTL)
│   ├── models/
│   │   └── egress_xgb_v1.pkl    # Trained XGBoost model (gitignored if large)
│   ├── training/
│   │   ├── train.py             # Training script
│   │   ├── evaluate.py          # MAE/RMSE evaluation
│   │   └── data/                # Training datasets (gitignored)
│   ├── tests/
│   │   ├── test_features.py
│   │   └── test_model.py
│   ├── Dockerfile
│   └── requirements.txt
│
├── contracts/
│   └── schemas.py               # Shared Pydantic types (mirrors Go contracts)
├── data/
│   ├── raw/                     # ShanghaiTech, UCSD datasets (gitignored)
│   └── synthetic/               # Simulator replay frames
├── docker-compose.yml           # Starts all three services + dependencies
├── Makefile
└── README.md                    # This file
```

---

## Services

### 1. `argus-cv` — Crowd Density Service

Accepts a base64-encoded camera frame and a list of zone bounding boxes. Returns per-zone occupancy counts and density estimates.

**Endpoint:** `POST /infer/density`

**Request:**
```json
{
  "frame_b64": "<base64-encoded JPEG string>",
  "frame_id": "frame_20250315_223104_001",
  "zones": [
    { "id": "zone_gate_b_north", "x1": 120, "y1": 80, "x2": 340, "y2": 290 },
    { "id": "zone_concourse_7",  "x1": 350, "y1": 80, "x2": 560, "y2": 290 }
  ]
}
```

**Response:**
```json
{
  "zones": [
    {
      "id": "zone_gate_b_north",
      "count": 184,
      "density_per_sqm": 4.2,
      "confidence": 0.91
    },
    {
      "id": "zone_concourse_7",
      "count": 67,
      "density_per_sqm": 1.8,
      "confidence": 0.88
    }
  ],
  "inference_ms": 287,
  "model_version": "yolov8n-v1"
}
```

**Model:** YOLOv8n (Ultralytics), pretrained on COCO dataset, person class only. No fine-tuning required.

**Latency target:** P95 < 300 ms on CPU, < 80 ms with CUDA GPU.

---

### 2. `argus-anomaly` — Behavioural Anomaly Detector

Analyses time-series density and flow vector data for a single zone. Detects three dangerous crowd signatures.

**Endpoint:** `POST /infer/anomaly`

**Request:**
```json
{
  "zone_id": "zone_gate_b_north",
  "density_history": [1.2, 1.4, 1.8, 2.6, 3.9, 4.8, 5.1],
  "flow_history": [
    { "vx": 0.4, "vy": -0.1 },
    { "vx": 0.9, "vy": -0.3 },
    { "vx": 1.8, "vy": -0.7 }
  ],
  "sample_interval_seconds": 5,
  "zone_area_sqm": 44.0
}
```

**Response:**
```json
{
  "zone_id": "zone_gate_b_north",
  "score": 0.89,
  "anomaly_type": "PANIC",
  "confidence": 0.87,
  "contributing_factors": [
    "density_gradient: 0.39/s (threshold: 0.30)",
    "velocity_magnitude: 2.4σ above baseline"
  ],
  "inference_ms": 12
}
```

**Anomaly types:**

| Type | Trigger condition |
|---|---|
| `PANIC` | Density gradient > 0.30/s AND velocity magnitude > 2σ above 60s baseline |
| `CRUSH_PRECURSOR` | Density > 4.0 persons/m² AND mean velocity < 0.2 m/s for > 15 s |
| `COUNTER_FLOW` | Angular standard deviation of flow vectors > 90° |
| `NONE` | No anomaly detected |

**Latency target:** P95 < 20 ms (pure NumPy, no model loading).

---

### 3. `argus-forecast` — Egress Congestion Forecaster

Predicts per-exit-gate congestion severity at T+2, T+5, and T+10 minutes given current venue state.

**Endpoint:** `POST /infer/egress`

**Request:**
```json
{
  "exit_gates": [
    {
      "id": "gate_b",
      "adjacent_zone_ids": ["zone_gate_b_north", "zone_concourse_7"],
      "current_density": 4.2,
      "density_30s_trend": 0.31,
      "flow_toward_exit": 0.74,
      "capacity": 1200
    }
  ],
  "event_end_minutes": 3,
  "venue_total_occupancy": 48200
}
```

**Response:**
```json
{
  "gates": [
    {
      "id": "gate_b",
      "t2_prob":  0.61,
      "t5_prob":  0.91,
      "t10_prob": 0.44,
      "severity_t5": "CRITICAL",
      "predicted_density_t5": 5.3,
      "time_to_critical_minutes": 4.8
    }
  ],
  "forecast_ms": 8,
  "model_version": "xgb-egress-v1"
}
```

**Severity thresholds:**

| Severity | Predicted density |
|---|---|
| `SAFE` | < 2.0 persons/m² |
| `ELEVATED` | 2.0 – 3.5 persons/m² |
| `WARNING` | 3.5 – 4.5 persons/m² |
| `CRITICAL` | > 4.5 persons/m² |

**Model:** XGBoost regressor, trained on ShanghaiTech egress replays + ARGUS simulator data. Features: `current_density`, `density_30s_trend`, `flow_toward_exit`, `zone_capacity`, `minutes_since_event_end`, `adjacent_zone_density`, `time_of_night`.

**Latency target:** P95 < 15 ms (cached responses within 2s TTL if inputs change < 5%).

---

## Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose v2
- 8 GB RAM minimum (16 GB recommended for running all three services)
- GPU optional but recommended for `argus-cv` in production

### Run with Docker (recommended)

```bash
# Clone the repo
git clone https://github.com/your-team/argus.git
cd argus/argus-ml

# Start all three ML services
docker compose up --build

# Verify all services are healthy
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
```

Expected health response:
```json
{
  "status": "ok",
  "model_loaded": true,
  "inference_count": 0,
  "uptime_seconds": 4.2
}
```

### Run locally (development)

```bash
# Install dependencies for a specific service
cd argus-cv
pip install -r requirements.txt

# Run the service
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Run tests
pytest tests/ -v
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `MODEL_PATH` | `models/` | Directory containing serialised model files |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`) |
| `CACHE_TTL_SECONDS` | `2` | Response cache TTL for `argus-forecast` |
| `YOLO_MODEL_VARIANT` | `yolov8n` | YOLOv8 variant (`yolov8n`, `yolov8s`) |
| `INFERENCE_WORKERS` | `2` | ThreadPoolExecutor size for CPU-bound inference |

---

## Model Details

### YOLOv8n (argus-cv)

| Property | Value |
|---|---|
| Architecture | YOLOv8 nano (Ultralytics) |
| Parameters | 3.2 M |
| Input size | 640 × 640 px |
| Training data | COCO 2017 (pretrained, no fine-tuning) |
| Inference device | CPU (CUDA auto-detected if available) |
| Mean latency (CPU) | ~220 ms |
| Mean latency (GPU) | ~28 ms |

### XGBoost Egress Regressor (argus-forecast)

| Property | Value |
|---|---|
| Algorithm | XGBoost gradient boosted trees |
| Features | 7 (see endpoint docs above) |
| Target | Density at gate in T+5 minutes (persons/m²) |
| Training set | 12,000 simulated egress sequences |
| Evaluation MAE (T+5) | 0.61 persons/m² |
| Evaluation RMSE (T+5) | 0.84 persons/m² |
| Inference time | < 5 ms |

### Training the egress model

```bash
cd argus-forecast/training

# Generate training data from simulator replays
python generate_dataset.py --scenarios 500 --output data/egress_train.csv

# Train and evaluate
python train.py --data data/egress_train.csv --output ../models/egress_xgb_v1.pkl

# Evaluate on held-out test set
python evaluate.py --model ../models/egress_xgb_v1.pkl --test data/egress_test.csv
```

---

## Evaluation

Benchmark results on a clean Docker environment (Intel i7-12700, no GPU):

| Service | P50 latency | P95 latency | P99 latency | Max throughput |
|---|---|---|---|---|
| `argus-cv` | 198 ms | 287 ms | 341 ms | 4.8 req/s |
| `argus-anomaly` | 8 ms | 14 ms | 19 ms | 180 req/s |
| `argus-forecast` | 5 ms | 11 ms | 16 ms | 240 req/s |

Anomaly detector accuracy on labelled scenario replays:

| Anomaly type | Precision | Recall | F1 |
|---|---|---|---|
| Panic | 0.91 | 0.88 | 0.89 |
| Crush precursor | 0.87 | 0.93 | 0.90 |
| Counter-flow | 0.79 | 0.82 | 0.80 |

---

## Testing

```bash
# Run all tests across all three services
make test

# Run tests for a specific service
cd argus-cv && pytest tests/ -v

# Run integration test (requires Docker Compose running)
make test-integration

# Run the demo scenario replay harness
python scripts/scenario_replay.py --scenario scenarios/egress_demo.yaml
```

The scenario replay harness plays back the scripted 8-minute egress scenario and asserts that each service produces the correct output at each timestep. All assertions must pass before the demo is recorded.

---

## Contracts

All request/response schemas are defined in `contracts/schemas.py` and mirror the Go backend contract definitions in `../contracts/README.md`. **Do not change schemas without coordinating with P1 (Go backend).** Any mismatch between Go's expected response and Python's actual response will silently produce wrong venue state data.

---

## Known Limitations

- `argus-cv` cold start takes ~15 seconds on first container launch (YOLOv8 model loading). The Go backend's circuit breaker handles this gracefully — requests during warmup return 503 and are retried.
- The egress model was trained on simulated data. Real-world performance will require retraining on actual venue egress observations.
- `argus-anomaly` counter-flow detection requires at least 10 flow history samples (50 seconds at 5s intervals) to produce a reliable result. Outputs before this window are marked with `confidence < 0.5`.
- All three services are CPU-only by default. For production deployment with live camera feeds, a CUDA-capable GPU is required to meet the 500 ms round-trip latency budget.

---

## Dependencies

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.0
ultralytics==8.2.0          # YOLOv8
numpy==1.26.4
pandas==2.2.2
scikit-learn==1.4.2
xgboost==2.0.3
opencv-python-headless==4.9.0.80
httpx==0.27.0               # async HTTP client
pytest==8.2.0
pytest-asyncio==0.23.6
```

---

## Team

| Role | Name | Responsibility |
|---|---|---|
| P1 — Go backend | Ananth Chavan | Event broker, venue state graph, REST API, WebSocket |
| P2 — Python ML | Akshat Kumar Jha | CV density, anomaly detection, egress forecasting |
| P3 — NLP + ops | Ishita | Operator assistant, paper, demo |
| P4 — Frontend | Anant Shrey | Digital twin map, dashboard, demo video |

---

## License

MIT License. See `LICENSE` for details.

---

*ARGUS · Autonomous Risk Governance and Unified Surveillance*