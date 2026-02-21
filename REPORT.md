# Agentic Task Extraction MVP — Technical Report

**Generated:** 2026-02-07

---

## 1. What This Project Does

This is a multimodal AI agent that takes images of official Persian letters, reads the text from them (OCR), extracts structured task information (task type, person name, national code, arguments), validates the extraction, asks a human operator for approval, and stores the results in a SQLite database. The entire flow is exposed through a Chainlit web UI with Persian (Farsi) localization.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph `StateGraph` with conditional edges, checkpointing, and interrupt-before HITL |
| LLM Provider | OpenRouter API (default model: Gemini 2.0 Flash) |
| OCR Agent | Dedicated multimodal LLM call with structured Pydantic output (`LetterOCR`) |
| Validator Agent | Separate multimodal LLM call with `with_structured_output(ValidationResult)` |
| Tools | Pydantic-validated `store_image`, `create_task`, `search_web`, `read_file` |
| Database | SQLite (`tasks.db` for tasks+images, `chat_history.db` for Chainlit persistence, `checkpoints.db` for LangGraph state) |
| UI | Chainlit with password auth, image upload, human approval buttons, auto-approve toggle, and a FastAPI task detail page |
| Language | Python 3.12 |

---

## 3. Project File Map

```
agent.py            — LangGraph StateGraph definition (nodes, edges, routing logic)
app.py              — Chainlit UI handlers + FastAPI task detail/edit page
ocr_agent.py        — OCR agent: image → structured LetterOCR Pydantic model
validator_agent.py  — Validator agent: compares extracted tasks against source image
tools.py            — Tool definitions, Pydantic validators, guardrails, executors
database.py         — SQLite schema init (images + tasks tables)
hitl.py             — Human-in-the-loop approval queue (request/approve/reject)
llm_client.py       — Low-level OpenRouter HTTP client (used for direct calls)
init_chat_db.py     — Chainlit chat history DB schema init
```

---

## 4. Agent Flow — Step by Step

The system has two execution paths. The `agent.py` StateGraph is the canonical pipeline. The `app.py` Chainlit handler also implements a direct procedural version. Both follow the same logical flow:

### 4.1 Image Upload

1. User uploads an image through the Chainlit UI.
2. `app.py` reads the file bytes, calls `store_image_directly()` to persist the raw image blob into the `images` table, and gets back an `image_id`.
3. The image is base64-encoded for LLM consumption.

### 4.2 OCR Node (`ocr_agent.py`)

4. The base64 image is sent to the multimodal LLM (Gemini via OpenRouter) with a specialized OCR prompt.
5. The prompt instructs the model to extract structured fields from a Persian official letter: `letter_number`, `letter_date`, `sender`, `recipient`, `subject`, `body`, `attachments`, `signature`, `raw_text`.
6. The LLM response is parsed (regex JSON extraction) into a `LetterOCR` Pydantic model.
7. The result is converted to a dict (null fields stripped) and displayed in the UI.

### 4.3 Task Extraction Node (`agent.py → extract_node`)

8. The OCR data + original base64 image are sent together to the multimodal LLM.
9. The prompt asks the model to extract a JSON array of tasks, each with: `task_type`, `full_name`, `national_code`, `arguments`, `image_id`.
10. If this is a retry (previous validation rejected), the prompt includes the rejection reason and correction instructions from the validator.
11. The LLM response is regex-parsed for a JSON array. Each task gets the `image_id` and `ocr_data` attached.

### 4.4 Validation Node (`validator_agent.py`)

12. The extracted tasks + original image are sent to a separate validator LLM call.
13. The validator uses `with_structured_output(ValidationResult)` to force the LLM to return a structured decision: `approve` or `reject`, with a reason and list of corrections.
14. Validation checks: task_type accuracy, name correctness, national code (10 digits), argument completeness.

### 4.5 Retry Logic (Conditional Edge)

15. If the validator rejects and `retry_count < 3`: the graph routes back to `increment_retry` → `extract_node`, passing the rejection feedback into the next extraction prompt.
16. If approved or retries exhausted: proceed to human approval.

### 4.6 Human Approval (HITL)

17. The graph uses LangGraph's `interrupt_before=["human_approval"]` to pause execution.
18. In the Chainlit UI, the extracted tasks are displayed to the operator with ✅ Approve / ❌ Cancel buttons.
19. If auto-approve is toggled on in settings, this step is skipped.
20. On approval, `resume_with_approval()` calls `graph.aupdate_state()` to set `human_approved=True` and resumes the graph.

### 4.7 Store Node

21. For each approved task, `execute_tool("create_task", task)` is called.
22. The tool validates args via `CreateTaskArgs` Pydantic model (national code must be 10 digits, etc.).
23. A row is inserted into the `tasks` table with status `pending`.
24. Results are streamed back to the UI with links to the task detail page.

### 4.8 Task Detail Page

25. Each stored task gets a web page at `/task/{id}` (served by FastAPI routes injected into Chainlit's app).
26. The page shows: all DB fields (editable), the OCR data (read-only), and the source image.
27. Operators can edit task fields and save via a PUT API at `/api/task/{id}`.

---

## 5. StateGraph Topology

```
                    ┌──────────────────────────────────┐
                    │           ENTRY POINT             │
                    └──────────────┬───────────────────┘
                                   ▼
                            ┌─────────────┐
                            │     OCR     │
                            └──────┬──────┘
                                   ▼
                            ┌─────────────┐
                            │   Extract   │◄──────────────┐
                            └──────┬──────┘               │
                                   ▼                      │
                            ┌─────────────┐               │
                            │  Validate   │               │
                            └──────┬──────┘               │
                                   ▼                      │
                          ┌────────────────┐              │
                          │  should_retry  │              │
                          └───┬─────┬──┬───┘              │
                  reject &    │     │  │                   │
                  retries < 3 │     │  │ error             │
                              ▼     │  ▼                   │
                    ┌──────────┐    │  END                 │
                    │increment │    │                      │
                    │  retry   │────┘──────────────────────┘
                    └──────────┘
                              │ approved
                              ▼
                  ┌──────────────────┐  (interrupt_before)
                  │ Human Approval   │
                  └────────┬─────────┘
                           ▼
                    ┌──────────────┐
                    │ should_store │
                    └───┬──────┬───┘
               approved │      │ rejected
                        ▼      ▼
                  ┌──────┐    END
                  │Store │
                  └──┬───┘
                     ▼
                    END
```

---

## 6. Tool Guardrails

All tools go through a validation pipeline in `tools.py`:

1. `validate_tool_args()` — Pydantic model validation per tool.
2. `requires_approval()` — Permission check (`store_image` and `create_task` are auto-approved; `search_web` and `read_file` require human approval).
3. `execute_tool()` — Validates then executes.

Specific validations:
- `CreateTaskArgs`: national_code must match `^\d{10}$`
- `StoreImageArgs`: filename must match `^[\w\-. ]+\.(jpg|jpeg|png|gif|webp)$`
- `ReadFileArgs`: no `..` or absolute paths (path traversal prevention)
- `SearchWebArgs`: query length 2–500 chars

---

## 7. Persistence

| Database | Purpose |
|---|---|
| `tasks.db` | `images` table (id, filename, blob, timestamp) + `tasks` table (id, task_type, full_name, national_code, arguments JSON, image_id FK, ocr_data JSON, status, timestamp) |
| `chat_history.db` | Chainlit conversation persistence (users, threads, steps, elements, feedbacks) |
| `checkpoints.db` | LangGraph async SQLite checkpointer for graph state persistence across interrupts |

---

## 8. Key Design Decisions

- **Two-agent validation loop**: A separate validator LLM re-examines the source image independently, catching extraction errors. Up to 3 retry cycles with feedback injection.
- **Structured output**: Both OCR and validation use Pydantic models to enforce schema compliance from LLM responses.
- **HITL via graph interrupt**: LangGraph's `interrupt_before` mechanism cleanly pauses the graph, letting the Chainlit UI collect human input before resuming.
- **Dual execution paths**: `app.py` contains both a graph-based flow (calling `process_image`/`resume_with_approval`) and a direct procedural flow. The procedural path in the second `@cl.on_message` handler is the one that actually runs (Python decorator override), calling OCR, extraction, and validation directly without the StateGraph.
- **OpenRouter abstraction**: Swapping models (Gemini, DeepSeek, etc.) requires only changing an env var.
