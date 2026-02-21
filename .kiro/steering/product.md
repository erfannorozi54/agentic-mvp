# Agentic Task Extraction MVP

## Overview
Multimodal LLM agent extracts tasks from Persian text images and populates a queue database. 
IMPORTANT: DO NOT CREATE NEW MARKDOWN FILES, YOU SHOULD ONLY UPDATE THE EXISTING ONES.

## Flow
1. User uploads image → Agent analyzes with multimodal LLM (Gemini/DeepSeek via OpenRouter)
2. Agent extracts: task type, full name, national code, arguments
3. Agent calls `store_image` → receives `image_id`
4. Agent calls `create_task` with extracted data + `image_id`

## Example
Image contains: "آزادسازی شماره تلفن - Alex Brown - کد ملی: 1384928471 - 09149257893"
→ Task record: `{task_type: "Unblock phone", full_name: "Alex Brown", national_code: "1384928471", arguments: {phone: "09149257893"}, image_id: 42}`

## Data Models
**Task:** `id, task_type, full_name, national_code, arguments, image_id, status, created_at`
**Image:** `id, filename, data, uploaded_at`

## Implementation Status
✅ LangGraph ReAct agent with Chain-of-Thought
✅ State management (message persistence)
✅ Tools: `store_image_tool`, `create_task_tool`
✅ SQLite databases (tasks + images)
✅ Input validation & guardrails
✅ Chainlit UI with image upload
✅ Real-time tool execution logs
✅ Human approval flow for tools
✅ Visual status indicators

## Next Steps
- Observability (Langfuse)
- Test with real Persian images
- Error handling & retries
