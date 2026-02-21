# LangChain Development Guidelines

**Installed versions:**
- langchain-core: 1.2.8
- langgraph: 1.0.7
- year 2026

Before writing any LangChain/LangGraph Python code:

1. Use the **doc-specialist** agent to search the LangChain/LangGraph documentation
2. Verify import paths and method signatures against the docs returned by doc-specialist

LangChain APIs change frequently between versions. Do not assume syntax from training data is current.
