import logging
import os
from datetime import datetime

os.makedirs("logs", exist_ok=True)

logger = logging.getLogger("agent")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s | %(levelname)-5s | %(name)s | %(message)s")
    fh = logging.FileHandler(f"logs/agent_{datetime.now():%Y%m%d}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
