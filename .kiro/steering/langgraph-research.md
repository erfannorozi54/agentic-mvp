# LangGraph Research Guidelines

## Context
- Project: Persian document OCR and task extraction agent
- LangGraph: 1.0.7+
- LangChain-core: 1.2.8
- Year: 2026

## Current Implementation
Using `create_react_agent` from `langgraph.prebuilt` with:
- Vision-to-task extraction agent
- Validator agent for quality control
- SQLite persistence
- Chainlit UI with human-in-the-loop

## Research Focus
Search LangGraph and LangChain documentation, forums, and web resources for:

1. **State Management**: StateGraph patterns, checkpointing, persistence
2. **Multi-Agent Coordination**: Supervisor patterns, handoffs, message passing
3. **Error Handling**: Retries, fallbacks, conditional edges
4. **Tool Execution**: Best practices for tool calling and validation
5. **Memory & Context**: Conversation history, state persistence across sessions

## Output Format
Provide:
- Specific LangGraph features/classes to use
- Minimal code examples
- Links to official documentation
- Comparison: current approach vs recommended approach
