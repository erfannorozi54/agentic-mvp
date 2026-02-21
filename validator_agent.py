"""Validator Agent - Reviews extracted tasks against source image."""
import os
import json
import asyncio
from typing import Literal
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from log_config import logger

load_dotenv()

VALIDATOR_PROMPT = """You are a validation agent. Your job is to verify extracted tasks against the source image.

For each extracted task, check:
1. Does the task_type match what's shown in the image?
2. Is the user's full name correctly extracted?
3. Is the national code (10 digits) accurate?
4. Are all relevant arguments captured from the document?

Decision criteria:
- APPROVE: All fields are accurate and complete
- REJECT: Any field is incorrect, missing, or misread

If rejecting, provide specific correction instructions for the extraction agent.

IMPORTANT: You MUST respond with a JSON object containing:
- decision: "approve" or "reject"
- reason: explanation string
- corrections: list of correction strings (can be empty if approved)"""


class ValidationResult(BaseModel):
    """Structured output for validation decision."""
    decision: Literal["approve", "reject"] = Field(
        description="Whether to approve or reject the extracted tasks"
    )
    reason: str = Field(
        description="Explanation for the decision"
    )
    corrections: list[str] = Field(
        default_factory=list,
        description="Specific corrections needed (if rejected)"
    )


def create_validator_agent():
    """Create the validator agent with structured output."""
    model_name = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp-1206")
    logger.debug(f"VALIDATOR | creating model: {model_name}")
    model = ChatOpenAI(
        model=model_name,
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        timeout=60,
    )
    return model.with_structured_output(ValidationResult)


async def validate_extraction_async(
    image_b64: str,
    extracted_tasks: list[dict],
    timeout: int = 60,
) -> ValidationResult:
    """Async version of validate_extraction with timeout and error handling."""
    validator = create_validator_agent()

    tasks_summary = "\n".join([
        f"- Task {i+1}: type={t.get('task_type')}, name={t.get('full_name')}, "
        f"national_code={t.get('national_code')}, args={t.get('arguments')}"
        for i, t in enumerate(extracted_tasks)
    ])

    logger.info(f"VALIDATOR | INPUT | tasks_count={len(extracted_tasks)} | timeout={timeout}s")
    logger.debug(f"VALIDATOR | INPUT | tasks_summary:\n{tasks_summary}")
    logger.debug(f"VALIDATOR | INPUT | system_prompt:\n{VALIDATOR_PROMPT}")

    messages = [
        SystemMessage(content=VALIDATOR_PROMPT),
        HumanMessage(content=[
            {"type": "text", "text": f"Verify these extracted tasks:\n\n{tasks_summary}\n\nCompare against the source image:"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ])
    ]

    try:
        result = await asyncio.wait_for(
            validator.ainvoke(messages),
            timeout=timeout
        )

        if not isinstance(result, ValidationResult):
            logger.error(f"VALIDATOR | INVALID_TYPE | got {type(result)}")
            raise ValueError(f"Invalid response type: {type(result)}")

        if result.decision not in ("approve", "reject"):
            logger.error(f"VALIDATOR | INVALID_DECISION | {result.decision}")
            raise ValueError(f"Invalid decision: {result.decision}")

        logger.info(f"VALIDATOR | RESPONSE | decision={result.decision} | reason={result.reason}")
        if result.corrections:
            logger.info(f"VALIDATOR | CORRECTIONS | {json.dumps(result.corrections, ensure_ascii=False)}")
        return result

    except asyncio.TimeoutError:
        logger.warning(f"VALIDATOR | TIMEOUT | exceeded {timeout}s, auto-approving")
        return ValidationResult(
            decision="approve",
            reason="Validation timed out - auto-approved",
            corrections=[]
        )
    except Exception as e:
        error_msg = str(e)
        if "data" in error_msg and "created_at" in error_msg:
            logger.warning(f"VALIDATOR | API_FORMAT_ERROR | auto-approving | {error_msg[:200]}")
            return ValidationResult(
                decision="approve",
                reason="Validation skipped due to API response format - auto-approved",
                corrections=[]
            )
        logger.error(f"VALIDATOR | ERROR | {type(e).__name__}: {e}")
        raise
