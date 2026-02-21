# Agentic MVP Stack

| Component | Choice | Notes |
|-----------|--------|-------|
| Orchestration | LangGraph | ReAct agent with state management |
| Multimodal LLM | OpenRouter API | Gemini 2.0 Flash (default), supports DeepSeek |
| Tools | store_image, create_task | Pydantic validation + guardrails |
| Database | SQLite | tasks.db (tasks + images tables) |
| UI | Chainlit | Image upload, tool logs, approval flow, status indicators |
| Observability | Langfuse | Agent tracing (pending) |
