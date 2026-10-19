import logging
import time

from fastapi import FastAPI, HTTPException

from app.config import get_settings
from app.extract import extract
from app.llm import LLMError
from app.schemas import ExtractRequest, ExtractResponse, TriageRequest, TriageResponse
from app.triage import triage_keywords

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Клинический компас — ML", version="0.1.0")


@app.get("/health")
def health():
    s = get_settings()
    return {"status": "ok", "llm_base_url": s.llm_base_url, "llm_model": s.llm_model}


@app.post("/extract", response_model=ExtractResponse)
def extract_endpoint(body: ExtractRequest):
    start = time.perf_counter()
    try:
        result = extract(body.text)
    except LLMError as e:
        raise HTTPException(502, str(e)) from e
    except Exception as e:  # LLM-сервер недоступен и т. п.
        raise HTTPException(503, f"LLM недоступна: {e}") from e
    return ExtractResponse(result=result, model=get_settings().llm_model,
                           elapsed_ms=(time.perf_counter() - start) * 1000)


@app.post("/triage", response_model=TriageResponse)
def triage_endpoint(body: TriageRequest):
    return triage_keywords(body.text)
