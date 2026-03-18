# ⚡ AI Copilot

An IDE-style AI coding assistant powered by Ollama (qwen3-coder) with MCP tool support, streaming chat, and repo-aware context.

![AI Copilot Screenshot](docs/images/chat-ui.png)

---

## ✨ Features

| Feature | Description |
|---|---|
| **Streaming Chat** | SSE + WebSocket real-time responses |
| **MCP Tool System** | Safe/dangerous tool classification with permission layer |
| **Repo Explorer** | Browse, search, and read workspace files |
| **Code Editor** | Syntax-highlighted editor with AI analysis |
| **Execution Timeline** | Visual step-by-step view of tool calls |
| **Session Memory** | Stateful conversation context per session |
| **Structured Logging** | Key=value log format for Grafana / Loki |

---

## 🚀 Quickstart

```bash
git clone <repo>
cd ai-copilot

# 1. Copy environment config
cp .env.example .env
# Edit .env: set LLM_BASE_URL to your Ollama instance

# 2. Start everything
docker compose up

# OR run locally:
make install
make dev
```

Open **http://localhost:5173**

---

## 🏗 Architecture

```
backend/
  app.py                    ← App factory, structured logging, lifecycle
  routes.py                 ← HTTP handlers (Pydantic-validated requests)
  copilot_engine.py         ← Thin façade (delegates to service layer)
  llm_client.py             ← Ollama API client (streaming + non-streaming)
  config.py                 ← Environment-based config
  copilot/
    conversation_manager.py ← Stateful session store (history, tool memory)
    prompt_builder.py       ← Template-based prompt construction
    tool_selector.py        ← Tool detection, permission layer, timeout guard
    response_streamer.py    ← SSE / WebSocket response helpers
  services/
    chat_service.py         ← Chat pipeline business logic
    repo_service.py         ← Repository operations
    tool_service.py         ← Tool execution + safety enforcement
    repo_analyzer.py        ← Repo stats & dependency detection
    code_debugger.py        ← Error parsing & debug prompts
  mcp/
    registry.py             ← Tool registry with metadata & category
    tools/
      repo_tools.py         ← list_files, read_file, write_file, search (safe/dangerous)
      code_tools.py         ← run_linter, run_tests, format_code (dangerous)
      dev_tools.py          ← GitHub issues, Jira, commit (dangerous)
  prompts/
    system_prompt.txt       ← Main system prompt template
    tool_prompt.txt         ← Tool calling instructions
    repo_analysis.txt       ← Repository analysis prompt

frontend/
  src/
    stores/
      chatStore.js          ← Chat messages, streaming, timeline events
      repoStore.js          ← File tree, search, repo stats
      toolStore.js          ← Tool list, execution, confirmation flow
    store/
      copilotStore.js       ← Backward-compat façade over sub-stores
    components/
      ChatPanel.vue         ← Streaming markdown chat
      CodeEditor.vue        ← Syntax-highlighted editor
      RepoExplorer.vue      ← File browser + search
      ToolOutput.vue        ← Tool runner with safe/dangerous badges
      ToolTimeline.vue      ← Visual execution timeline ✨ NEW
    services/
      api.js                ← SSE + WebSocket + REST helpers
```

---

## 🔧 Tool Permission System

Tools are classified as **safe** (auto-executed) or **dangerous** (require confirmation):

| Safe Tools | Dangerous Tools |
|---|---|
| list_files | write_file |
| read_file | run_tests |
| search_repository | run_linter |
| scan_directory | format_code |
| list_issues | commit_code |
| | create_github_issue |
| | create_jira_ticket |

The AI only auto-runs safe tools. Dangerous tools surface a confirmation prompt in the Tools panel.

---

## 🛠 Development

```bash
make dev          # start backend + frontend
make lint         # run all linters
make format       # auto-format all code
make test         # run Python tests
make clean        # remove build caches
make help         # show all commands
```

Pre-commit hooks (auto-format on git commit):
```bash
pip install pre-commit
pre-commit install
```

---

## 🌐 API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/chat` | Streaming chat (SSE) |
| GET  | `/api/ws/chat` | Streaming chat (WebSocket) |
| POST | `/api/code/analyze` | Analyze code (SSE) |
| POST | `/api/code/generate` | Generate code (SSE) |
| POST | `/api/code/debug` | Debug code (SSE) |
| GET  | `/api/tools` | List tools with categories |
| POST | `/api/tools/run` | Run a tool (`force=true` for dangerous) |
| GET  | `/api/repo/files` | List workspace files |
| GET  | `/api/repo/read` | Read a file |
| POST | `/api/repo/search` | Search repo |
| GET  | `/api/repo/analyze` | Repo statistics |
| GET  | `/api/sessions` | Active sessions |
| POST | `/api/sessions/clear` | Clear session |
| GET  | `/health` | Health check |

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_BASE_URL` | `http://10.1.60.120:11434` | Ollama server URL |
| `LLM_MODEL` | `qwen3-coder:latest` | Model to use |
| `ALLOWED_BASE_PATH` | `/tmp/copilot-workspace` | Workspace root |
| `MAX_FILE_SIZE_MB` | `10` | Max readable file size |
| `DEBUG` | `false` | Enable debug logging |
