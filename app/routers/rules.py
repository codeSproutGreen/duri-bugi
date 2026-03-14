from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CategoryRule
from app.schemas import RuleOut, RuleUpdate

router = APIRouter(prefix="/api", tags=["rules"])


def _to_out(rule: CategoryRule) -> dict:
    return RuleOut(
        id=rule.id,
        merchant_pattern=rule.merchant_pattern,
        debit_account_id=rule.debit_account_id,
        credit_account_id=rule.credit_account_id,
        debit_account_name=rule.debit_account.name if rule.debit_account else None,
        credit_account_name=rule.credit_account.name if rule.credit_account else None,
        hit_count=rule.hit_count,
    )


@router.get("/rules")
def list_rules(db: Session = Depends(get_db)):
    rules = db.query(CategoryRule).order_by(CategoryRule.hit_count.desc()).all()
    return [_to_out(r) for r in rules]


@router.put("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: int, data: RuleUpdate, db: Session = Depends(get_db)):
    rule = db.query(CategoryRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")

    provided = data.model_fields_set
    if 'merchant_pattern' in provided:
        rule.merchant_pattern = data.merchant_pattern
    if 'debit_account_id' in provided:
        rule.debit_account_id = data.debit_account_id
    if 'credit_account_id' in provided:
        rule.credit_account_id = data.credit_account_id

    db.commit()
    db.refresh(rule)
    return _to_out(rule)


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(CategoryRule).get(rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    db.delete(rule)
    db.commit()
    return {"status": "deleted"}
