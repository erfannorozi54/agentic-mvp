"""OCR Agent - Extracts structured text from official Persian letters."""
import os
import json
import re
import asyncio
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
from log_config import logger

load_dotenv()


class LetterOCR(BaseModel):
    """Structured OCR output for official Persian letters."""
    letter_number: str | None = None
    letter_date: str | None = None
    sender: str | None = None
    recipient: str | None = None
    subject: str | None = None
    body: str | None = None
    attachments: list[str] | None = None
    signature: str | None = None
    raw_text: str | None = None


OCR_PROMPT = """You are an OCR agent specialized in Persian official letters.
Extract ALL text from this image and structure it into these fields:

- letter_number: شماره نامه (document number)
- letter_date: تاریخ (date in Persian calendar)
- sender: فرستنده (sender organization/person)
- recipient: گیرنده (recipient organization/person)  
- subject: موضوع (subject line)
- body: متن نامه (main body text)
- attachments: پیوستها (list of attachments if mentioned)
- signature: امضا (signature/stamp info)
- raw_text: Complete raw text from the image

Return valid JSON only. Use null for missing fields."""


def create_ocr_model():
    model_name = os.getenv("OCR_MODEL", "google/gemini-2.0-flash-001")
    logger.debug(f"OCR | creating model: {model_name}")
    return ChatOpenAI(
        model=model_name,
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )


async def extract_letter_ocr(image_b64: str, timeout: int = 60) -> LetterOCR:
    """Extract structured text from official letter image."""
    model = create_ocr_model()
    img_preview = f"{len(image_b64)} chars b64"

    logger.info(f"OCR | INPUT | image={img_preview} | prompt={len(OCR_PROMPT)} chars | timeout={timeout}s")
    logger.debug(f"OCR | INPUT | prompt:\n{OCR_PROMPT}")

    messages = [HumanMessage(content=[
        {"type": "text", "text": OCR_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
    ])]

    try:
        response = await asyncio.wait_for(model.ainvoke(messages), timeout=timeout)
        content = response.content
        logger.info(f"OCR | RESPONSE | length={len(content)} chars")
        logger.debug(f"OCR | RESPONSE | raw:\n{content}")

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            data = json.loads(json_match.group())
            result = LetterOCR(**data)
            logger.info(f"OCR | PARSED | fields={[k for k,v in result.model_dump().items() if v is not None]}")
            logger.debug(f"OCR | PARSED | data={json.dumps(data, ensure_ascii=False, indent=2)}")
            return result

        logger.warning(f"OCR | PARSE_FAIL | no JSON found in response")
    except asyncio.TimeoutError:
        logger.error(f"OCR | TIMEOUT | exceeded {timeout}s")
    except json.JSONDecodeError as e:
        logger.error(f"OCR | JSON_ERROR | {e}")
    except Exception as e:
        logger.error(f"OCR | ERROR | {type(e).__name__}: {e}")

    return LetterOCR(raw_text="OCR extraction failed")


def ocr_to_dict(ocr: LetterOCR) -> dict:
    """Convert LetterOCR to dict, excluding None values."""
    return {k: v for k, v in ocr.model_dump().items() if v is not None}
