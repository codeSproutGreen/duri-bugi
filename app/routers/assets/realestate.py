"""Real estate asset management."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import RealEstate
from app.schemas import RealEstateCreate, RealEstateUpdate

router = APIRouter(prefix="/api/assets", tags=["assets-realestate"])


@router.get("/realestate")
def list_realestate(db: Session = Depends(get_db)):
    items = db.query(RealEstate).order_by(RealEstate.sort_order, RealEstate.id).all()
    return [{"id": r.id, "name": r.name, "value": r.value, "memo": r.memo, "updated_at": r.updated_at} for r in items]


@router.post("/realestate")
def create_realestate(data: RealEstateCreate, db: Session = Depends(get_db)):
    r = RealEstate(name=data.name, value=data.value, memo=data.memo)
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "name": r.name, "value": r.value, "memo": r.memo, "updated_at": r.updated_at}


@router.put("/realestate/{rid}")
def update_realestate(rid: int, data: RealEstateUpdate, db: Session = Depends(get_db)):
    r = db.query(RealEstate).get(rid)
    if not r:
        raise HTTPException(404)
    if data.name is not None:
        r.name = data.name
    if data.value is not None:
        r.value = data.value
    if data.memo is not None:
        r.memo = data.memo
    r.updated_at = datetime.now().isoformat()
    db.commit()
    return {"id": r.id, "name": r.name, "value": r.value, "memo": r.memo, "updated_at": r.updated_at}


@router.delete("/realestate/{rid}")
def delete_realestate(rid: int, db: Session = Depends(get_db)):
    r = db.query(RealEstate).get(rid)
    if not r:
        raise HTTPException(404)
    db.delete(r)
    db.commit()
    return {"ok": True}
