from fastapi import APIRouter, Depends, HTTPException

from app.kb import KnowledgeBase, Scale, Source, get_kb
from app.security import current_user

router = APIRouter(prefix="/api/kb", tags=["kb"], dependencies=[Depends(current_user)])


@router.get("/scales", response_model=list[Scale])
def list_scales(kb: KnowledgeBase = Depends(get_kb)):
    return list(kb.scales.values())


@router.get("/scales/{scale_id}", response_model=Scale)
def get_scale(scale_id: str, kb: KnowledgeBase = Depends(get_kb)):
    if scale_id not in kb.scales:
        raise HTTPException(404, "Шкала не найдена")
    return kb.scales[scale_id]


@router.get("/sources", response_model=dict[str, Source])
def list_sources(kb: KnowledgeBase = Depends(get_kb)):
    return kb.sources
