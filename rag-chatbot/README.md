# DocSearch AI — RAG-Powered PDF Chatbot

A production-quality **Retrieval-Augmented Generation (RAG)** chatbot that lets users upload PDF documents and ask natural-language questions about their content. The system semantically retrieves the most relevant passages and uses an LLM to generate grounded, cited answers.

```
┌────────────────────────────────────────────────────────────────────┐
│                          Architecture                              │
│                                                                    │
│  PDF Upload ──► Text Extraction ──► Chunking ──► Embedding         │
│                                                        │           │
│                                                   Vector Store     │
│                                                        │           │
│  User Query ──► Embed Query ──► Semantic Search ───────┘           │
│                                        │                           │
│                               Top-K Chunks + Metadata              │
│                                        │                           │
│                                   LLM Prompt                       │
│                                        │                           │
│                            Grounded Answer + Citations             │
└────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | React + Vite + Tailwind CSS | Fast builds, great DX, small bundle |
| Backend | FastAPI (async) | High throughput, OpenAPI docs auto-generated |
| LLM | OpenAI GPT-4o-mini via LangChain | Cost-effective, strong at following citations |
| Embeddings | `text-embedding-3-small` | 1536 dims, fast, inexpensive |
| Vector store | FAISS (dev) / Pinecone (prod) | FAISS = zero infra; Pinecone = managed cloud |
| PDF parsing | PyMuPDF (fitz) | Fast, no Java, preserves page numbers |
| Container | Docker + Docker Compose | Reproducible across environments |
| Frontend deploy | Vercel | Zero-config CDN + SPA routing |

---

## Quick Start (Local Dev)

### Prerequisites

- Python 3.11+
- Node.js 20+
- An OpenAI API key (`sk-...`)

### 1. Clone the repo

```bash
git clone https://github.com/your-org/rag-chatbot.git
cd rag-chatbot
```

### 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# → Edit .env and set OPENAI_API_KEY=sk-your-key

# Create data directories
mkdir -p data/uploads data/faiss_index

# Start the API server
uvicorn app.main:app --reload --port 8000
```

The API is now running at **http://localhost:8000**  
Interactive docs: **http://localhost:8000/api/docs**

### 3. Frontend setup

```bash
cd ../frontend
npm install

# Configure environment
cp .env.example .env
# VITE_API_URL=http://localhost:8000 (default — no change needed for local dev)

npm run dev
```

App is live at **http://localhost:3000**

---

## Usage

1. **Upload** — Drag-and-drop a PDF (or click to browse). The backend extracts text, chunks it, embeds the chunks, and stores them in the vector index. You'll see a confirmation with page count and chunk count.

2. **Select** — Check the documents you want to query (you can search across multiple documents simultaneously).

3. **Ask** — Type any natural-language question. The system:
   - Embeds your question with the same model used for documents
   - Retrieves the top-5 semantically similar chunks
   - Injects those chunks into a grounded system prompt
   - Returns an answer that cites the exact filename and page number

4. **Explore sources** — Click "N sources cited" below each answer to inspect the retrieved passages and their relevance scores.

---

## Configuration Reference

All backend config is via environment variables (see `backend/.env.example`):

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI secret key |
| `LLM_MODEL` | `gpt-4o-mini` | Change to `gpt-4o` for better quality |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | 1536-dim embeddings |
| `VECTOR_STORE_TYPE` | `faiss` | `faiss` or `pinecone` |
| `CHUNK_SIZE` | `1000` | Characters per chunk |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks |
| `MAX_RETRIEVAL_CHUNKS` | `5` | k nearest neighbours per query |
| `MAX_FILE_SIZE_MB` | `50` | PDF upload size limit |
| `RATE_LIMIT_PER_MINUTE` | `20` | Per-IP request cap |
| `ALLOWED_ORIGINS` | `[localhost:3000, ...]` | CORS whitelist |

---

## Switching to Pinecone (Production)

1. Create a Pinecone account and index (dimension: `1536`, metric: `cosine`)
2. Set in `.env`:
   ```
   VECTOR_STORE_TYPE=pinecone
   PINECONE_API_KEY=your-key
   PINECONE_ENVIRONMENT=us-east-1-aws
   PINECONE_INDEX_NAME=rag-chatbot
   ```
3. Install extra dependency: `pip install pinecone-client langchain-pinecone`

---

## Docker Deployment

```bash
# Build and start all services
cp backend/.env.example backend/.env
# → Fill in OPENAI_API_KEY in backend/.env

docker compose up --build -d

# Check logs
docker compose logs -f backend

# Stop
docker compose down
```

Services:
- **Backend**: `http://localhost:8000`
- **Frontend**: `http://localhost:3000`

Data persists in named Docker volumes (`rag_uploads`, `rag_faiss`).

---

## Vercel Deployment (Frontend)

### Option A — Vercel CLI

```bash
cd frontend
npm i -g vercel
vercel

# Set environment variable:
# VITE_API_URL = https://your-backend-host.com
```

### Option B — Vercel Dashboard

1. Import the `frontend/` directory as a new Vercel project
2. Set Build Command: `npm run build`
3. Set Output Directory: `dist`
4. Add environment variable: `VITE_API_URL` → your backend URL

> **CORS**: After deploying, add your Vercel URL to `ALLOWED_ORIGINS` in the backend `.env`.

---

## Backend Cloud Deployment Options

The FastAPI backend can be deployed to:

| Platform | Notes |
|---|---|
| **Railway** | Push Dockerfile; set env vars in dashboard |
| **Render** | Free tier available; auto-deploy from GitHub |
| **Fly.io** | Global edge deployment, great for latency |
| **AWS ECS** | Full control; pair with EFS for persistent volumes |
| **Google Cloud Run** | Serverless container; use GCS for file storage |

For cloud deployment, replace FAISS with **Pinecone** (FAISS stores indexes on local disk, which doesn't work across ephemeral container instances).

---

## Project Structure

```
rag-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, middleware, routers
│   │   ├── api/
│   │   │   ├── documents.py     # Upload / list / delete endpoints
│   │   │   ├── chat.py          # Query endpoint
│   │   │   └── health.py        # Health check
│   │   ├── core/
│   │   │   ├── config.py        # Pydantic Settings (env vars)
│   │   │   └── rate_limiter.py  # Sliding-window rate limiter
│   │   ├── models/
│   │   │   └── schemas.py       # Request/response Pydantic models
│   │   └── services/
│   │       ├── document_processor.py  # PDF → chunks → vectors
│   │       ├── vector_store.py        # FAISS / Pinecone abstraction
│   │       └── rag_chain.py           # Retrieval + LLM orchestration
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.tsx             # Full React app + all components
│   │   ├── types/index.ts       # TypeScript domain types
│   │   ├── services/api.ts      # Typed API client
│   │   └── hooks/useChat.ts     # Chat state management hook
│   ├── index.html
│   ├── vite.config.ts
│   ├── vercel.json
│   ├── Dockerfile.prod          # Nginx production container
│   └── .env.example
├── docker-compose.yml           # Full-stack local/server deployment
└── README.md
```

---

## Security Practices Implemented

- **API keys**: Never exposed to frontend; backend reads from env vars only
- **Input validation**: Pydantic models validate all request payloads with type checking and constraints
- **File validation**: Extension check + MIME type check + size limit + empty file guard
- **Path traversal**: `Path(filename).name` strips any directory components from uploaded filenames
- **Rate limiting**: Per-IP sliding window (minute + hour) before any computation runs
- **CORS**: Explicit allowlist; wildcard only in development
- **Error messages**: Generic 500 responses in production (no stack traces leaked)
- **Non-root Docker**: Backend runs as `appuser`, not root

---

## Potential Enhancements (Post-MVP)

### Streaming responses
```python
# In rag_chain.py — use astream() instead of ainvoke()
async def answer_stream(request: ChatRequest):
    async for chunk in self.llm.astream(messages):
        yield chunk.content
```
On the frontend, use `EventSource` or `fetch` with `ReadableStream`.

### Conversation summarisation
When history exceeds N turns, summarise older context:
```python
summarizer = ChatOpenAI(model="gpt-4o-mini")
summary = await summarizer.ainvoke([
    SystemMessage("Summarise this conversation in 100 words"),
    *old_messages
])
# Inject summary as a SystemMessage instead of raw history
```

### Multi-file management UI
- File tagging and collections
- Per-document chat threads
- Bulk upload with progress tracking

### Authentication
Add JWT-based auth with FastAPI Users or Auth0:
```python
from fastapi_users import FastAPIUsers
# Each user gets isolated document namespaces in the vector store
```

### Hybrid search
Combine BM25 (keyword) with dense embeddings for better recall:
```python
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
retriever = EnsembleRetriever(
    retrievers=[bm25, dense],
    weights=[0.3, 0.7]
)
```

### Answer confidence scoring
Use logprobs from the OpenAI API to estimate answer confidence and flag low-confidence responses.

### Async document processing queue
For large PDFs, use Celery + Redis to process uploads in the background and notify the frontend via WebSocket when indexing is complete.

---

## License

MIT
