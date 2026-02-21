import sqlite3
import json
import re
from typing import Any
from pydantic import BaseModel, field_validator
from database import DB_PATH
from log_config import logger


class CreateTaskArgs(BaseModel):
    task_type: str
    full_name: str | None = None
    national_code: str | None = None
    arguments: dict | None = None
    image_id: int | None = None
    ocr_data: dict | None = None

    @field_validator("national_code")
    @classmethod
    def validate_national_code(cls, v):
        if v and not re.match(r'^\d{10}$', v):
            raise ValueError("National code must be 10 digits")
        return v


TOOL_VALIDATORS = {
    "create_task": CreateTaskArgs,
}


def validate_tool_args(tool_name: str, args: dict) -> tuple[bool, Any]:
    """Guardrail: validate tool arguments. Returns (success, validated_args_or_error)."""
    validator = TOOL_VALIDATORS.get(tool_name)
    if not validator:
        logger.error(f"TOOL | UNKNOWN | {tool_name}")
        return False, f"Unknown tool: {tool_name}"
    try:
        return True, validator(**args)
    except Exception as e:
        logger.warning(f"TOOL | VALIDATION_FAIL | {tool_name} | {e}")
        return False, str(e)


def store_image_directly(filename: str, data: bytes) -> int:
    """Store image directly to database and return image_id."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO images (filename, data, uploaded_at) VALUES (?, ?, datetime('now'))",
        (filename, data)
    )
    image_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"TOOL:store_image | image_id={image_id} filename={filename} size={len(data)} bytes")
    return image_id


def create_task(args: CreateTaskArgs) -> dict:
    """Create a new task record in the queue database."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO tasks (task_type, full_name, national_code, arguments, image_id, ocr_data) VALUES (?, ?, ?, ?, ?, ?)",
        (args.task_type, args.full_name, args.national_code,
         json.dumps(args.arguments, ensure_ascii=False) if args.arguments else None,
         args.image_id,
         json.dumps(args.ocr_data, ensure_ascii=False) if args.ocr_data else None)
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"TOOL:create_task | task_id={task_id} type={args.task_type} name={args.full_name} nc={args.national_code} image_id={args.image_id}")
    logger.debug(f"TOOL:create_task | args={json.dumps(args.arguments, ensure_ascii=False) if args.arguments else None}")
    return {"task_id": task_id, "status": "pending"}


TOOL_EXECUTORS = {
    "create_task": create_task,
}


def execute_tool(tool_name: str, args: dict) -> tuple[bool, dict]:
    """Execute tool with guardrail validation. Returns (success, result)."""
    logger.debug(f"TOOL | EXECUTE | {tool_name} | input_keys={list(args.keys())}")
    valid, validated = validate_tool_args(tool_name, args)
    if not valid:
        logger.error(f"TOOL | REJECTED | {tool_name} | {validated}")
        return False, {"error": validated}

    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        logger.error(f"TOOL | NO_EXECUTOR | {tool_name}")
        return False, {"error": f"No executor for {tool_name}"}

    result = executor(validated)
    logger.debug(f"TOOL | RESULT | {tool_name} | {result}")
    return True, result
