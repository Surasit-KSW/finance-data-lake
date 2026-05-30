"""
routers/simulation.py — Production cost simulation endpoints

All calculations are done server-side in simulation_service.py.
Frontend sends raw inputs (BOM, yields, RM layers) → receives pre-calculated results.

Endpoints:
    POST /api/v1/simulate/gi          — GI Plant 1300 full simulation
    POST /api/v1/simulate/pipe        — Pipe A1 (1100) or A2 (1200)
    POST /api/v1/simulate/rm-forecast — RM FIFO MAP forecast (all materials)
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

from backend.services.simulation_service import (
    calc_gi_simulation,
    calc_pipe_simulation,
    calc_rm_forecast,
)

router = APIRouter(prefix="/api/v1/simulate", tags=["Simulation"])


# ── Request models ────────────────────────────────────────────────────────────

class GISimulateRequest(BaseModel):
    """GI Plant 1300 inputs — mirrors Zustand store GI fields"""
    volume:       float = 15000
    pkYield:      float = 99.80
    crYield:      float = 99.03
    giYield:      float = 99.80
    pkItems:      list[dict[str, Any]] = []
    crItems:      list[dict[str, Any]] = []
    giItems:      list[dict[str, Any]] = []
    revenueItems: list[dict[str, Any]] = []
    rmCostItems:  list[dict[str, Any]] = []
    capexItems:   list[dict[str, Any]] = []
    sgaPercent:   float = 3.5
    taxRate:      float = 20.0


class PipeSimulateRequest(BaseModel):
    """Pipe Plant inputs — pass the full Zustand store state, specify plant"""
    plant: str  # '1100' or '1200'
    state: dict[str, Any]  # full store state (uses p1100* or p1200* fields)
    gicMAP: float = 0.0    # pre-calculated GIC MAP from GI simulation


class RmForecastRequest(BaseModel):
    """RM FIFO forecast inputs"""
    rmStockLayers:        dict[str, list[dict[str, Any]]] = {}
    rmMonthlyConsumption: dict[str, float] = {}
    months: int = 12
    # Optional: include GI state to derive GIC MAP
    giState: dict[str, Any] | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/gi")
def simulate_gi(req: GISimulateRequest):
    """GI Plant 1300 full cost simulation"""
    try:
        result = calc_gi_simulation(req.model_dump())
        return {"status": "ok", "plant": "1300", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pipe")
def simulate_pipe(req: PipeSimulateRequest):
    """Pipe A1 (1100) or A2 (1200) cost simulation"""
    if req.plant not in ("1100", "1200"):
        raise HTTPException(status_code=400, detail="plant must be '1100' or '1200'")
    try:
        state = {**req.state, "gicMAP": req.gicMAP}
        result = calc_pipe_simulation(req.plant, state)
        return {"status": "ok", "plant": req.plant, "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rm-forecast")
def simulate_rm_forecast(req: RmForecastRequest):
    """RM FIFO MAP forecast for all materials"""
    try:
        state = {
            "rmStockLayers":        req.rmStockLayers,
            "rmMonthlyConsumption": req.rmMonthlyConsumption,
        }
        if req.giState:
            state.update(req.giState)
        result = calc_rm_forecast(state, req.months)
        return {"status": "ok", "data": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
