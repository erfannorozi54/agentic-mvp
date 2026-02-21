"""Production-ready multi-agent graph with StateGraph, HITL, streaming, and persistence."""
import os
import json
import re
from typing import Annotated, Literal
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver as SqliteSaver
import aiosqlite
from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI

from ocr_agent import extract_letter_ocr, ocr_to_dict
from validator_agent import validate_extraction_async
from tools import execute_tool
from log_config import logger

load_dotenv()


class AgentState(TypedDict):
    """State for task extraction workflow."""
    messages: Annotated[list, add_messages]
    image_b64: str
    image_id: int
    filename: str
    ocr_data: dict
    extracted_tasks: list[dict]
    validation_result: dict | None
    retry_count: int
    human_approved: bool
    final_tasks: list[dict] | None
    error: str | None


async def ocr_node(state: AgentState) -> dict:
    """Extract OCR data from image."""
    logger.info(f"NODE:ocr | START | image_id={state['image_id']} filename={state['filename']}")
    try:
        ocr_result = await extract_letter_ocr(state["image_b64"], timeout=60)
        ocr_data = ocr_to_dict(ocr_result)
        logger.info(f"NODE:ocr | DONE | fields={list(ocr_data.keys())}")
        return {
            "ocr_data": ocr_data,
            "messages": [AIMessage(content=f"OCR extracted: {list(ocr_data.keys())}")]
        }
    except Exception as e:
        logger.error(f"NODE:ocr | ERROR | {type(e).__name__}: {e}")
        return {"error": f"OCR failed: {e}", "messages": [AIMessage(content=f"OCR error: {e}")]}


async def extract_node(state: AgentState) -> dict:
    """Extract tasks using multimodal LLM with OCR context."""
    retry = state.get("retry_count", 0)
    logger.info(f"NODE:extract | START | image_id={state['image_id']} retry={retry}")
    try:
        model_name = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
        model = ChatOpenAI(
            model=model_name,
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )

        ocr_json = json.dumps(state["ocr_data"], ensure_ascii=False, indent=2)
        prompt = f"""Extract tasks from Persian document. OCR Data:
{ocr_json}

Return JSON array: [{{"task_type":"...","full_name":"...","national_code":"...","arguments":{{...}},"image_id":{state["image_id"]}}}]"""

        if state.get("validation_result") and state["validation_result"].get("decision") == "reject":
            prompt += f"\n\n⚠️ Previous attempt rejected:\n{state['validation_result']['reason']}"
            for c in state["validation_result"].get("corrections", []):
                prompt += f"\n- {c}"

        logger.info(f"NODE:extract | LLM_INPUT | model={model_name} | prompt_len={len(prompt)}")
        logger.debug(f"NODE:extract | LLM_INPUT | prompt:\n{prompt}")

        r = await model.ainvoke([
            HumanMessage(content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{state['image_b64']}"}}
            ])
        ])

        logger.info(f"NODE:extract | LLM_RESPONSE | length={len(r.content)}")
        logger.debug(f"NODE:extract | LLM_RESPONSE | raw:\n{r.content}")

        m = re.search(r'\[[\s\S]*\]', r.content)
        tasks = []
        if m:
            tasks = json.loads(m.group())
            for t in tasks:
                t['image_id'] = state["image_id"]
                t['ocr_data'] = state["ocr_data"]

        logger.info(f"NODE:extract | PARSED | tasks_count={len(tasks)}")
        for i, t in enumerate(tasks):
            logger.debug(f"NODE:extract | TASK[{i}] | {json.dumps(t, ensure_ascii=False, default=str)}")

        return {
            "extracted_tasks": tasks,
            "messages": [AIMessage(content=f"Extracted {len(tasks)} tasks")]
        }
    except Exception as e:
        logger.error(f"NODE:extract | ERROR | {type(e).__name__}: {e}")
        return {"error": f"Extraction failed: {e}", "messages": [AIMessage(content=f"Extraction error: {e}")]}


async def validate_node(state: AgentState) -> dict:
    """Validate extracted tasks against source image."""
    logger.info(f"NODE:validate | START | tasks_count={len(state['extracted_tasks'])}")
    try:
        if not state["extracted_tasks"]:
            logger.warning("NODE:validate | SKIP | no tasks to validate")
            return {
                "validation_result": {"decision": "reject", "reason": "No tasks extracted", "corrections": []},
                "messages": [AIMessage(content="Validation: No tasks to validate")]
            }

        v = await validate_extraction_async(state["image_b64"], state["extracted_tasks"], timeout=60)
        logger.info(f"NODE:validate | DONE | decision={v.decision} reason={v.reason}")
        return {
            "validation_result": {"decision": v.decision, "reason": v.reason, "corrections": v.corrections},
            "messages": [AIMessage(content=f"Validation: {v.decision} - {v.reason}")]
        }
    except Exception as e:
        logger.error(f"NODE:validate | ERROR | {type(e).__name__}: {e}")
        return {"error": f"Validation failed: {e}", "messages": [AIMessage(content=f"Validation error: {e}")]}


def human_approval_node(state: AgentState) -> dict:
    """Placeholder for human approval - actual approval via graph.update_state()."""
    logger.info(f"NODE:human_approval | WAITING | image_id={state['image_id']} tasks={len(state['extracted_tasks'])}")
    return {"messages": [AIMessage(content="Awaiting human approval...")]}


async def store_node(state: AgentState) -> dict:
    """Store validated tasks with retry logic."""
    logger.info(f"NODE:store | START | tasks_count={len(state['extracted_tasks'])} approved={state.get('human_approved')}")
    stored = []
    errors = []

    for i, task in enumerate(state["extracted_tasks"]):
        for attempt in range(3):
            try:
                ok, res = execute_tool("create_task", task)
                if ok:
                    stored.append(res)
                    logger.info(f"NODE:store | SAVED | task[{i}] task_id={res.get('task_id')}")
                    break
                else:
                    logger.warning(f"NODE:store | FAIL | task[{i}] attempt={attempt+1} error={res}")
                    if attempt == 2:
                        errors.append(f"Task failed: {res}")
            except Exception as e:
                logger.error(f"NODE:store | ERROR | task[{i}] attempt={attempt+1} {type(e).__name__}: {e}")
                if attempt == 2:
                    errors.append(f"Task error: {e}")

    logger.info(f"NODE:store | DONE | stored={len(stored)}/{len(state['extracted_tasks'])} errors={len(errors)}")
    return {
        "final_tasks": stored,
        "error": "; ".join(errors) if errors else None,
        "messages": [AIMessage(content=f"Stored {len(stored)}/{len(state['extracted_tasks'])} tasks")]
    }


def increment_retry(state: AgentState) -> dict:
    """Increment retry counter."""
    new_count = state.get("retry_count", 0) + 1
    logger.info(f"NODE:increment_retry | retry_count={new_count}")
    return {"retry_count": new_count}


def should_retry(state: AgentState) -> Literal["retry", "human_approval", "end"]:
    """Decide whether to retry extraction or proceed to approval."""
    if state.get("error"):
        logger.info(f"EDGE:should_retry | -> end (error: {state['error']})")
        return "end"

    if state.get("validation_result", {}).get("decision") == "reject":
        if state.get("retry_count", 0) < 3:
            logger.info(f"EDGE:should_retry | -> retry (rejected, attempt {state.get('retry_count', 0)+1})")
            return "retry"

    logger.info(f"EDGE:should_retry | -> human_approval")
    return "human_approval"


def should_store(state: AgentState) -> Literal["store", "end"]:
    """Decide whether to store based on human approval."""
    approved = state.get("human_approved")
    dest = "store" if approved else "end"
    logger.info(f"EDGE:should_store | approved={approved} -> {dest}")
    return dest


_checkpointer = None

async def _get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        conn = await aiosqlite.connect("checkpoints.db")
        _checkpointer = SqliteSaver(conn)
        await _checkpointer.setup()
    return _checkpointer


async def create_agent():
    """Create production-ready graph with StateGraph, HITL, and persistence."""
    workflow = StateGraph(AgentState)

    workflow.add_node("ocr", ocr_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("increment_retry", increment_retry)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("store", store_node)

    workflow.set_entry_point("ocr")
    workflow.add_edge("ocr", "extract")
    workflow.add_edge("extract", "validate")
    workflow.add_conditional_edges("validate", should_retry, {"retry": "increment_retry", "human_approval": "human_approval", "end": END})
    workflow.add_edge("increment_retry", "extract")
    workflow.add_conditional_edges("human_approval", should_store, {"store": "store", "end": END})
    workflow.add_edge("store", END)

    checkpointer = await _get_checkpointer()
    return workflow.compile(checkpointer=checkpointer, interrupt_before=["human_approval"])


async def process_image(image_b64: str, image_id: int, filename: str):
    """Start extraction workflow, returns state and events."""
    logger.info(f"GRAPH | START | image_id={image_id} filename={filename} image_size={len(image_b64)} chars")
    graph = await create_agent()

    initial_state = {
        "messages": [],
        "image_b64": image_b64,
        "image_id": image_id,
        "filename": filename,
        "ocr_data": {},
        "extracted_tasks": [],
        "validation_result": None,
        "retry_count": 0,
        "human_approved": False,
        "final_tasks": None,
        "error": None
    }

    config = {"configurable": {"thread_id": f"img_{image_id}"}}

    events = []
    async for event in graph.astream(initial_state, config):
        node_name = list(event.keys())[0]
        val = event[node_name]
        keys = list(val.keys()) if isinstance(val, dict) else str(type(val).__name__)
        logger.debug(f"GRAPH | EVENT | node={node_name} keys={keys}")
        events.append(event)

    state = await graph.aget_state(config)
    logger.info(f"GRAPH | PAUSED | image_id={image_id} next={state.next} error={state.values.get('error')}")
    return state.values, events


async def resume_with_approval(image_id: int, approved: bool):
    """Resume workflow after human approval."""
    logger.info(f"GRAPH | RESUME | image_id={image_id} approved={approved}")
    graph = await create_agent()
    config = {"configurable": {"thread_id": f"img_{image_id}"}}

    await graph.aupdate_state(config, {"human_approved": approved})

    events = []
    async for event in graph.astream(None, config):
        node_name = list(event.keys())[0]
        val = event[node_name]
        keys = list(val.keys()) if isinstance(val, dict) else str(type(val).__name__)
        logger.debug(f"GRAPH | EVENT | node={node_name} keys={keys}")
        events.append(event)

    state = await graph.aget_state(config)
    final_tasks = state.values.get("final_tasks", [])
    logger.info(f"GRAPH | COMPLETE | image_id={image_id} stored={len(final_tasks)} error={state.values.get('error')}")
    return state.values, events
