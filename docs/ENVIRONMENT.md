# CALLFLOW AI — Environment Configuration & Secrets Management

> **Platform Version:** 1.0.0-PROD-SPEC  
> **Target Environments:** Local Development (`development`), Staging (`staging`), Production (`production`)

---

## 1. Environment Variable Reference Matrix

All backend configuration variables are loaded and strictly validated at startup using **Pydantic Settings** (`BaseSettings`). Missing mandatory variables halt startup immediately.

### 1.1 Core Application & Gateway

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `APP_ENV` | `string` | `development` | Environment mode (`development`, `staging`, `production`). | Yes |
| `APP_NAME` | `string` | `CallFlow AI` | Service name identifier for logs and metrics. | No |
| `DEBUG` | `boolean` | `false` | Enables verbose stack traces. Must be `false` in production. | Yes |
| `PORT` | `integer` | `8000` | Port for FastAPI application server. | No |
| `HOST` | `string` | `0.0.0.0` | Bind interface address. | No |
| `BASE_URL` | `string` | `http://localhost:8000`| Publicly accessible base URL (used for webhooks and callbacks). | Yes |
| `CORS_ORIGINS` | `string` | `http://localhost:3000`| Comma-separated list of allowed frontend origins. | Yes |
| `JWT_SECRET` | `string` | *(None)* | High-entropy 256-bit secret used to sign session access tokens. | Yes |
| `JWT_ALGORITHM` | `string` | `HS256` | Token signing algorithm (`HS256` or `RS256`). | No |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`| `integer` | `15` | Expiration lifetime of access token. | No |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `integer` | `7` | Expiration lifetime of refresh token. | No |
| `ENCRYPTION_MASTER_KEY` | `string` | *(None)* | 32-byte Base64 key for AES-GCM database field encryption. | Yes |

---

### 1.2 PostgreSQL Database Tier

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `DATABASE_URL` | `string` | *(None)* | Async connection string: `postgresql+asyncpg://user:pass@host:5432/callflow` | Yes |
| `DB_POOL_SIZE` | `integer` | `20` | Maximum number of permanent connections in the pool. | No |
| `DB_MAX_OVERFLOW` | `integer` | `10` | Temporary burst connections allowed above `DB_POOL_SIZE`. | No |
| `DB_POOL_TIMEOUT` | `integer` | `30` | Seconds to wait before raising pool exhaustion error. | No |
| `DB_ECHO` | `boolean` | `false` | Logs all raw SQL queries. Must be `false` in production. | No |

---

### 1.3 Redis In-Memory State & Pub/Sub

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `REDIS_URL` | `string` | `redis://localhost:6379/0` | Redis URI connection string. In prod: `rediss://...` with TLS. | Yes |
| `REDIS_POOL_SIZE` | `integer` | `50` | Maximum active socket connections in Redis pool. | No |
| `REDIS_SOCKET_TIMEOUT` | `float` | `5.0` | Socket read/write timeout in seconds. | No |

---

### 1.4 AI Models & OpenAI Realtime Voice

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `OPENAI_API_KEY` | `string` | *(None)* | OpenAI Secret API key (`sk-proj-...`). | Yes |
| `OPENAI_REALTIME_MODEL` | `string` | `gpt-4o-realtime-preview-2024-10-01` | Realtime voice model identifier. | Yes |
| `OPENAI_EMBEDDING_MODEL` | `string` | `text-embedding-3-small` | Model for knowledge base vectorization. | Yes |
| `OPENAI_SUMMARY_MODEL` | `string` | `gpt-4o-mini` | Cost-effective LLM for post-call analysis extraction. | Yes |
| `OPENAI_DEFAULT_VOICE` | `string` | `alloy` | Default voice preset (`alloy`, `ash`, `ballad`, `coral`, `echo`, `sage`, `shimmer`, `verse`). | No |

---

### 1.5 Telephony & Twilio Integration

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `TWILIO_ACCOUNT_SID` | `string` | *(None)* | Twilio Account identifier (`AC...`). | Yes |
| `TWILIO_AUTH_TOKEN` | `string` | *(None)* | Twilio primary authentication token (used for signature validation). | Yes |
| `TWILIO_DEFAULT_PHONE_NUMBER`| `string` | *(None)* | Default E.164 caller ID number for outbound campaigns. | Yes |
| `TWILIO_MEDIA_STREAM_WS_URL`| `string` | *(None)* | Public WSS endpoint for Twilio streams (e.g. `wss://api.callflow.ai/ws/media-stream`). | Yes |

---

### 1.6 Vector Database (Qdrant)

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `QDRANT_HOST` | `string` | `localhost` | Hostname of Qdrant instance. | Yes |
| `QDRANT_PORT` | `integer` | `6333` | REST / gRPC port for Qdrant. | No |
| `QDRANT_API_KEY` | `string` | *(None)* | API authentication key for managed Qdrant Cloud. | If using Cloud |
| `QDRANT_COLLECTION_NAME` | `string` | `callflow_knowledge_base`| Vector collection name. | No |

---

### 1.7 Object Storage (S3 / MinIO)

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `S3_ENDPOINT_URL` | `string` | *(Optional)* | Custom endpoint if using MinIO or Cloudflare R2. Omit for AWS. | No |
| `S3_REGION_NAME` | `string` | `us-east-1` | Cloud storage region. | Yes |
| `S3_BUCKET_NAME` | `string` | `callflow-recordings` | S3 bucket name for audio recordings and uploaded docs. | Yes |
| `AWS_ACCESS_KEY_ID` | `string` | *(None)* | IAM credentials for S3 bucket access. | Yes |
| `AWS_SECRET_ACCESS_KEY` | `string` | *(None)* | IAM secret for S3 bucket access. | Yes |

---

### 1.8 Automation & External Integrations (n8n)

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `N8N_WEBHOOK_BASE_URL` | `string` | `http://localhost:5678/webhook` | Base URL for triggering automated n8n workflows. | Yes |
| `N8N_API_KEY` | `string` | *(None)* | Secret token authenticating CallFlow to n8n webhook triggers. | Yes |

---

### 1.9 Observability & Diagnostics

| Variable | Type | Default | Description | Required in Prod |
|---|---|---|---|---|
| `LOG_LEVEL` | `string` | `INFO` | Logging threshold (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | No |
| `SENTRY_DSN` | `string` | *(Optional)* | Sentry project DSN for exception tracking. | Staging / Prod |
| `OTEL_EXPORTER_OTLP_ENDPOINT`| `string` | *(Optional)* | OpenTelemetry collector endpoint for traces and metrics. | Optional |

---

## 2. Sample `.env.example` Template

```bash
# ------------------------------------------------------------------------------
# CALLFLOW AI - Environment Configuration Template
# Copy this file to .env and replace placeholder values.
# DO NOT COMMIT .env TO VERSION CONTROL.
# ------------------------------------------------------------------------------

# Application
APP_ENV=development
APP_NAME="CallFlow AI"
DEBUG=true
PORT=8000
HOST=0.0.0.0
BASE_URL="http://localhost:8000"
CORS_ORIGINS="http://localhost:3000"
JWT_SECRET="replace-with-a-64-character-random-hex-string-for-local-dev-only"
JWT_ALGORITHM=HS256
ENCRYPTION_MASTER_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

# PostgreSQL
DATABASE_URL="postgresql+asyncpg://callflow_user:callflow_pass@localhost:5432/callflow_db"
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# Redis
REDIS_URL="redis://localhost:6379/0"

# OpenAI
OPENAI_API_KEY="sk-proj-your-openai-api-key-here"
OPENAI_REALTIME_MODEL="gpt-4o-realtime-preview-2024-10-01"
OPENAI_EMBEDDING_MODEL="text-embedding-3-small"
OPENAI_SUMMARY_MODEL="gpt-4o-mini"
OPENAI_DEFAULT_VOICE="alloy"

# Twilio
TWILIO_ACCOUNT_SID="ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
TWILIO_AUTH_TOKEN="your_twilio_auth_token_here"
TWILIO_DEFAULT_PHONE_NUMBER="+18005550199"
TWILIO_MEDIA_STREAM_WS_URL="wss://your-ngrok-or-domain.ngrok-free.app/ws/media-stream"

# Qdrant
QDRANT_HOST="localhost"
QDRANT_PORT=6333
QDRANT_COLLECTION_NAME="callflow_knowledge_base"

# Object Storage (MinIO local or S3)
S3_ENDPOINT_URL="http://localhost:9000"
S3_REGION_NAME="us-east-1"
S3_BUCKET_NAME="callflow-audio-recordings"
AWS_ACCESS_KEY_ID="minioadmin"
AWS_SECRET_ACCESS_KEY="minioadmin"

# Automation (n8n)
N8N_WEBHOOK_BASE_URL="http://localhost:5678/webhook"
N8N_API_KEY="your-n8n-webhook-auth-key"

# Monitoring
LOG_LEVEL="INFO"
```

---

## 3. Secret Rotation & Key Lifecycle Protocol

1. **Zero Secret Commits Guarantee:**
   - Pre-commit hooks (`gitleaks`, `detect-secrets`) are enforced to reject any commits containing API keys, private keys, or passwords.
2. **Dynamic Credential Rotation:**
   - `JWT_SECRET` rotation: Supports dual-key verification during a 24-hour transition period.
   - Twilio Tokens & OpenAI Keys: Stored as ciphertext in the database. Rotating a tenant's integration key requires calling the re-encryption utility without restarting backend nodes.
3. **Local Development Tunnels (ngrok / Cloudflare Tunnel):**
   - In local development, Twilio requires an internet-accessible webhook URL. Developers run `ngrok http 8000` and supply the resulting HTTPS and WSS endpoints into `BASE_URL` and `TWILIO_MEDIA_STREAM_WS_URL`.
