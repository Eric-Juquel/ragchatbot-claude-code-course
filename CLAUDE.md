# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# Quick start (from repo root)
./run.sh

# Manual start
cd backend && uv run uvicorn app:app --reload --port 8000
```

Web UI: `http://localhost:8000` — API docs: `http://localhost:8000/docs`

Requires a `.env` file in the repo root with `ANTHROPIC_API_KEY=...`.

## Dependencies

```bash
uv sync   # Install all dependencies
```

> **Important**: Always use `uv` to run Python commands (e.g., `uv run ...`). Never use `pip` directly.

No test suite exists in this codebase.

## Architecture

The app is split into `backend/` (Python/FastAPI) and `frontend/` (vanilla JS/HTML/CSS). Course documents live in `docs/` and are loaded into ChromaDB on startup.

### Agentic RAG Pattern

The core design uses **Claude as an agent** that decides when to search:

1. `POST /api/query` → `app.py` resolves/creates session, calls `RAGSystem.query()`
2. `rag_system.py` builds prompt, fetches session history, calls `AIGenerator.generate_response()` with the `search_course_content` tool available
3. **Claude API call #1**: Claude answers directly OR emits a `tool_use` block
4. If tool use: `ToolManager.execute_tool()` → `CourseSearchTool.execute()` → `VectorStore.search()` → ChromaDB semantic search returns chunks
5. **Claude API call #2**: Claude synthesizes chunks into final answer (no tools this time)
6. Sources and response return up the chain; session history updated

### Two-Collection Vector Store

`VectorStore` (`vector_store.py`) maintains two ChromaDB collections:
- **`course_catalog`**: One document per course (title, instructor, link). Used for fuzzy course-name resolution via semantic search before filtering content.
- **`course_content`**: Chunked lesson text with metadata (`course_title`, `lesson_number`, `chunk_index`). This is what gets queried for answers.

Course name resolution (`_resolve_course_name`) runs a semantic search against `course_catalog` to find the canonical title, then uses that as an exact filter on `course_content`. This allows partial/fuzzy course names from Claude to match correctly.

### Document Format

Course documents in `docs/` must follow this structure for `DocumentProcessor` to parse them correctly:

```
Course Title: [title]
Course Link: [url]
Course Instructor: [instructor]

Lesson 0: [title]
Lesson Link: [url]
[content...]

Lesson 1: [title]
...
```

### Session Management

Each chat session gets a UUID. `SessionManager` stores the last `MAX_HISTORY` (default 2) exchanges per session, which are injected into the system prompt (not as message history) for each API call.

### Key Configuration (`backend/config.py`)

| Setting | Default | Purpose |
|---------|---------|---------|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | LLM for generation |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | SentenceTransformers model for ChromaDB |
| `CHUNK_SIZE` | 800 | Characters per content chunk |
| `CHUNK_OVERLAP` | 100 | Overlap between chunks |
| `MAX_RESULTS` | 5 | Max search results returned to Claude |
| `MAX_HISTORY` | 2 | Conversation exchanges remembered per session |
| `CHROMA_PATH` | `./chroma_db` | Persisted ChromaDB location (relative to `backend/`) |

### Adding New Tools

Tools follow the `Tool` ABC in `search_tools.py` — implement `get_tool_definition()` (returns Anthropic tool schema) and `execute(**kwargs)`. Register with `tool_manager.register_tool(your_tool)` in `rag_system.py`. If the tool tracks sources, add a `last_sources` list attribute for `ToolManager.get_last_sources()` to pick up.
