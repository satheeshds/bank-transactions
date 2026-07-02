# Mail2Firefly Refactored Architecture

Professional FastAPI project structure with clean separation of concerns.

## Final Directory Structure

```
mail2firefly/
├── app/                           # Main application package
│   ├── __init__.py
│   ├── main.py                    # FastAPI app instance
│   ├── config.py                  # Configuration loading
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── schemas.py         # Pydantic request/response models
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── status.py
│   │           ├── sync.py
│   │           ├── logs.py
│   │           ├── transactions.py
│   │           └── rules.py
│   ├── db/
│   │   ├── __init__.py
│   │   └── session.py             # Database operations
│   ├── models/
│   │   └── __init__.py            # Data models
│   └── services/
│       ├── __init__.py
│       ├── firefly_client.py      # Firefly API client
│       ├── firefly_builder.py     # Transaction builder
│       ├── imap.py                # IMAP client
│       ├── parser.py              # Email parser
│       └── service.py             # Orchestrator
│
├── cli/                           # CLI & Background Workers
│   ├── __init__.py
│   ├── main.py                    # CLI entry point (uv run python -m cli.main)
│   └── sync_worker.py             # Background sync orchestrator
│
├── frontend/                      # Vue 3 + Vite (separate npm workspace)
│   ├── package.json
│   ├── vite.config.js
│   ├── src/
│   │   ├── main.js
│   │   ├── components/
│   │   └── views/
│   └── index.html
│
├── static/                        # Frontend build output
│   └── dist/                      # Built by: npm run build
│
├── data/                          # Runtime data
│   └── mail2firefly.db            # SQLite database
│
├── tests/                         # Unit & integration tests
│   ├── __init__.py
│   ├── conftest.py                # Pytest configuration
│   ├── test_api.py
│   ├── test_services.py
│   └── test_db.py
│
├── web.py                         # FastAPI entry point (thin wrapper)
├── README.md                      # Project overview
├── REFACTORING.md                 # This file
├── config.example.toml            # Example configuration
├── config.toml                    # User configuration
├── pyproject.toml                 # Python metadata
├── docker-compose.yml             # Optional: Docker setup
├── .gitignore                     # Git ignore rules
└── uv.lock                        # UV lock file
```

## Key Improvements

### 1. **Clean Root Directory**
Only essential files:
- `web.py` — FastAPI entry point
- `README.md`, `REFACTORING.md` — Documentation
- Config files — `config.toml`, `pyproject.toml`
- `docker-compose.yml`, `.gitignore` — Setup files

**Deleted legacy files:**
- ❌ `config.py` (root) → moved to `app/config.py`
- ❌ `service.py` (root) → moved to `app/services/service.py`
- ❌ `database.py` (root) → moved to `app/db/session.py`
- ❌ `models.py` (root) → moved to `app/models/__init__.py`
- ❌ `parser.py` (root) → moved to `app/services/parser.py`
- ❌ `firefly_client.py` (root) → moved to `app/services/firefly_client.py`
- ❌ `firefly.py` (root) → moved to `app/services/firefly_builder.py`
- ❌ `imap_client.py` (root) → moved to `app/services/imap.py`
- ❌ `main.py` (root) → moved to `cli/main.py`
- ❌ `sync_worker.py` (root) → moved to `cli/sync_worker.py`

### 2. **New `cli/` Package**
Dedicated package for CLI and background workers:
```bash
# Run sync from CLI
uv run python -m cli.main

# Import in code
from cli.sync_worker import start_sync_background
from cli.main import main
```

### 3. **New `data/` Directory**
Centralized location for runtime data:
- SQLite database: `data/mail2firefly.db`
- Optional: logs, cache, temp files

### 4. **New `tests/` Directory**
Structure mirrors app for easy testing:
- `conftest.py` — Pytest fixtures and configuration
- `test_api.py` — HTTP endpoint tests
- `test_services.py` — Business logic tests
- `test_db.py` — Database operation tests

### 5. **Updated Imports**
All endpoints now import from cli:
```python
# Before
import sync_worker

# After
from cli import sync_worker
```

## API Endpoints

All endpoints are available under both versioned and legacy routes:

| Endpoint | Method | Purpose | Versions |
|----------|--------|---------|----------|
| `/api/v1/status` | GET | Connectivity & statistics | ✅ v1, legacy |
| `/api/v1/sync` | POST | Trigger background sync | ✅ v1, legacy |
| `/api/v1/logs` | GET | Fetch execution logs | ✅ v1, legacy |
| `/api/v1/transactions` | GET | List transactions | ✅ v1, legacy |
| `/api/v1/rules` | GET | List parsing rules | ✅ v1, legacy |

**Legacy routes still work:**
```bash
curl http://localhost:8000/api/status    # → /api/v1/status
curl http://localhost:8000/api/sync      # → /api/v1/sync
```

## Usage

### Start FastAPI Server
```bash
cd c:\Users\david\source\bank-transactions

# Terminal 1: FastAPI server
uv run uvicorn web:app --host 127.0.0.1 --port 8000

# Terminal 2: Vite dev server (optional, for frontend)
cd frontend
npm run dev
```

### Run CLI Sync
```bash
# One-time sync run
uv run python -m cli.main

# With direct imports (in your code)
from cli.main import main
main()
```

### Test Endpoints
```bash
# Status endpoint
curl http://127.0.0.1:8000/api/status

# New v1 endpoint
curl http://127.0.0.1:8000/api/v1/status

# List transactions
curl http://127.0.0.1:8000/api/v1/transactions?limit=50

# Trigger sync
curl -X POST http://127.0.0.1:8000/api/v1/sync
```

## Development Workflow

### Add a New Endpoint
1. Create handler in `app/api/v1/endpoints/new_feature.py`
2. Define Pydantic model in `app/api/v1/schemas.py`
3. Add business logic to `app/services/`
4. Import and register router in `app/main.py`

### Add a New Service
1. Create module in `app/services/new_service.py`
2. Implement core logic (no HTTP dependencies)
3. Import in endpoint handlers or `cli/main.py`

### Add Tests
```bash
# Create test file
touch tests/test_new_feature.py

# Run tests
uv run pytest tests/
```

## Benefits

✅ **Clean Architecture** — Separation of HTTP, business logic, and data layers  
✅ **Testable** — Services have no HTTP dependency, easy to unit test  
✅ **Reusable** — Call services from CLI, workers, scheduled tasks, or tests  
✅ **Maintainable** — Clear responsibility boundaries, intuitive imports  
✅ **Scalable** — Easy to add v2 API, new endpoints, background workers, or microservices  
✅ **Type-safe** — Pydantic schemas for request/response validation  
✅ **Backward Compatible** — Legacy `/api/*` endpoints still work  
✅ **Professional** — Matches FastAPI best practices and industry standards  

## Checklist Completed

- [x] Create `app/` package (main application)
- [x] Create `cli/` package (CLI & background workers)
- [x] Create `tests/` package (unit tests)
- [x] Create `data/` directory (runtime data)
- [x] Move all services to `app/services/`
- [x] Move database to `app/db/session.py`
- [x] Move models to `app/models/__init__.py`
- [x] Move CLI to `cli/main.py` and `cli/sync_worker.py`
- [x] Delete all legacy files from root
- [x] Update all imports across the codebase
- [x] Update `app/api/v1/endpoints/` to import from `cli.sync_worker`
- [x] Verify imports work
- [x] Verify FastAPI server starts
- [x] Verify endpoints respond (backward compatible)
- [x] Update documentation

## File Locations Reference

### App Package
- Config: `app/config.py`
- Database: `app/db/session.py`
- Models: `app/models/__init__.py`
- Services: `app/services/*.py`
- API Endpoints: `app/api/v1/endpoints/*.py`

### CLI
- Entry Point: `cli/main.py`
- Background Worker: `cli/sync_worker.py`

### Frontend
- Vue App: `frontend/src/`
- Built Output: `static/dist/`

### Configuration
- Main Config: `config.toml` (in project root)
- Example: `config.example.toml`
- Database: `data/mail2firefly.db`

### Entry Points
- **Web**: `uv run uvicorn web:app` → `web.py` → `app/main.py`
- **CLI**: `uv run python -m cli.main` → `cli/main.py`

## Future Improvements

1. **Error Handling** — Add middleware for consistent error responses
2. **Logging** — Configure structured logging in `app/config.py`
3. **Authentication** — Add API key or JWT auth middleware
4. **Database Migrations** — Add Alembic for schema management
5. **Async** — Convert sync functions to async where beneficial
6. **Monitoring** — Add health check endpoints and metrics
7. **Docker** — Use `Dockerfile` for containerization
8. **CI/CD** — Add GitHub Actions for automated testing

## Notes

- All imports now use `app.`, `cli.` package namespaces
- Configuration file (`config.toml`) remains in project root
- Database location: `data/mail2firefly.db` (configurable)
- Frontend builds to: `static/dist/` (unchanged)
- All legacy `/api/*` routes forward to `/api/v1/*` routes
