import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import anamnesis, auth, doctor, kb, patient, ws
from app.config import get_settings
from app.kb import get_kb
from app.services.alerts import rules_schedule

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("compass")


@asynccontextmanager
async def lifespan(_: FastAPI):
    kb_ = get_kb()  # падаем при старте, если база знаний невалидна
    log.info("kb loaded: %d scales, %d rules, %d drugs", len(kb_.scales), len(kb_.rules), len(kb_.drugs))
    minutes = get_settings().rules_check_minutes
    schedule = asyncio.create_task(rules_schedule(kb_, minutes)) if minutes > 0 else None
    yield
    if schedule:
        schedule.cancel()


app = FastAPI(title="Клинический компас", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def response_time(request: Request, call_next):
    """Время ответа — техметрика кейса: пишем в заголовок и лог."""
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time-ms"] = f"{ms:.1f}"
    log.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code, ms)
    return response


@app.get("/api/health")
def health():
    return {"status": "ok"}


for r in (auth.router, kb.router, patient.router, doctor.router, anamnesis.doctor_router, anamnesis.patient_router,
          ws.router):
    app.include_router(r)
