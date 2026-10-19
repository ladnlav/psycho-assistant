from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.db import SessionLocal
from app.security import user_from_token
from app.services.alerts import hub

router = APIRouter()


@router.websocket("/ws/doctor")
async def doctor_alerts(ws: WebSocket, token: str):
    with SessionLocal() as db:
        try:
            user = user_from_token(db, token)
        except HTTPException:
            user = None
    if user is None or user.role != "doctor":
        await ws.close(code=4401)
        return
    await ws.accept()
    await hub.connect(user.id, ws)
    try:
        while True:
            await ws.receive_text()  # держим соединение; входящие сообщения не используются
    except WebSocketDisconnect:
        hub.disconnect(user.id, ws)
