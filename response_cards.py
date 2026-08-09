"""
Day 19 Step 3 — Pydantic response card schemas.

These models define the shape of structured data the backend can return
alongside (or instead of) a plain-text answer. The frontend renders them
as bordered cards rather than inline text, giving claim-status lookups
and coverage summaries a clean, scannable layout.
"""

from pydantic import BaseModel
from typing import Optional


class ClaimStatusCard(BaseModel):
    """Rendered when the user asks about a specific claim."""
    claim_id: str
    status: str
    amount: Optional[float] = None
    date: Optional[str] = None


class CoverageSummaryCard(BaseModel):
    """Rendered when the user asks whether a service is covered."""
    plan_name: str
    deductible: Optional[float] = None
    copay: Optional[float] = None
    covered: Optional[bool] = None
