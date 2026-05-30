"""
services/simulation_service.py — Production cost calculation engine (Python port)

Ported from fintech-command-center/src/lib/simulation-engine.js
All calculations happen server-side; frontend only sends inputs and renders results.
"""
from __future__ import annotations
from typing import Any


# ── Core calculation ──────────────────────────────────────────────────────────

def calc_process_cost(items: list[dict], vol_in: float) -> dict:
    """
    คำนวณต้นทุนรวมของ 1 process (Work Center)

    Args:
        items: cost items — each has 'type' ('variable'|'fixed'),
               'consumption', 'unitPrice' (for variable) or 'amount' (for fixed)
        vol_in: input volume MT for variable cost calculation

    Returns:
        { var_cost, fix_cost, total }
    """
    var_cost = 0.0
    fix_cost = 0.0
    for item in items:
        if item.get("type") == "variable":
            var_cost += float(item.get("consumption") or 0) * float(item.get("unitPrice") or 0) * vol_in
        else:
            fix_cost += float(item.get("amount") or 0)
    return {"var_cost": round(var_cost, 2), "fix_cost": round(fix_cost, 2), "total": round(var_cost + fix_cost, 2)}


def forecast_map(layers: list[dict], monthly_consumption: float, months: int = 12) -> list[dict]:
    """
    FIFO MAP Forecast — simulate stock consumption layer by layer

    Args:
        layers: [{ id, qty_mt, unit_value_thb }] oldest first (FIFO order)
        monthly_consumption: MT consumed per month
        months: number of months to forecast

    Returns:
        [{ month: int, map: float, remaining_qty: float }]
    """
    remaining = [dict(l) for l in layers]  # deep copy
    result = []

    for m in range(months):
        consume = monthly_consumption

        for layer in remaining:
            if consume <= 0:
                break
            take = min(float(layer.get("qty_mt", 0)), consume)
            layer["qty_mt"] = float(layer["qty_mt"]) - take
            consume -= take

        remaining = [l for l in remaining if float(l.get("qty_mt", 0)) > 0]

        total_qty = sum(float(l.get("qty_mt", 0)) for l in remaining)
        total_val = sum(float(l.get("qty_mt", 0)) * float(l.get("unit_value_thb", 0)) for l in remaining)
        current_map = total_val / total_qty if total_qty > 0 else 0.0

        result.append({
            "month": m + 1,
            "map": round(current_map, 2),
            "remaining_qty": round(total_qty, 2),
        })

    return result


def get_forecast_price(rm_stock_layers: dict, rm_monthly_consumption: dict, material: str) -> float:
    """Next month's MAP price for a given RM material via FIFO forecast."""
    layers = rm_stock_layers.get(material, [])
    consumption = rm_monthly_consumption.get(material, 0)
    if not layers or not consumption:
        return 0.0
    result = forecast_map(layers, consumption, 1)
    return result[0]["map"] if result else 0.0


# ── GI Plant 1300 ─────────────────────────────────────────────────────────────

def calc_gi_simulation(state: dict) -> dict:
    """
    Full GI Plant 1300 simulation.
    Mirrors SimulationDashboard.jsx calculation logic.

    state fields: volume, pkYield, crYield, giYield,
                  pkItems, crItems, giItems, revenueItems, rmCostItems, capexItems,
                  sgaPercent, taxRate
    """
    volume   = float(state.get("volume", 0))
    pk_yield = float(state.get("pkYield", 100)) / 100
    cr_yield = float(state.get("crYield", 100)) / 100
    gi_yield = float(state.get("giYield", 100)) / 100

    vol_pk_out = volume * pk_yield
    vol_cr_out = vol_pk_out * cr_yield
    vol_gi_out = vol_cr_out * gi_yield

    # Process costs
    pk_cost = calc_process_cost(state.get("pkItems", []), vol_pk_out)
    cr_cost = calc_process_cost(state.get("crItems", []), vol_cr_out)
    gi_cost = calc_process_cost(state.get("giItems", []), vol_gi_out)

    # RM cost (per MT × volume)
    rm_total = sum(float(i.get("amount") or 0) for i in state.get("rmCostItems", [])) * volume

    # Depreciation (capex / lifeYears / 12 months)
    depre = sum(
        float(i.get("amount") or 0) / max(float(i.get("lifeYears") or 1) * 12, 1)
        for i in state.get("capexItems", [])
    )

    total_cost = rm_total + pk_cost["total"] + cr_cost["total"] + gi_cost["total"] + depre
    unit_cost  = round(total_cost / vol_gi_out, 2) if vol_gi_out > 0 else 0.0

    # Revenue
    avg_price   = sum(float(i.get("amount") or 0) for i in state.get("revenueItems", []))
    revenue     = avg_price * vol_gi_out
    sga_pct     = float(state.get("sgaPercent", 0)) / 100
    sga_cost    = revenue * sga_pct
    cogs        = total_cost + sga_cost
    gross_profit = revenue - total_cost
    ebit        = gross_profit - sga_cost
    tax_rate    = float(state.get("taxRate", 0)) / 100
    tax         = max(ebit * tax_rate, 0)
    net_income  = ebit - tax

    gic_map = total_cost / vol_gi_out if vol_gi_out > 0 else 0.0

    return {
        "volumes": {
            "input": round(volume, 2),
            "pk_out": round(vol_pk_out, 2),
            "cr_out": round(vol_cr_out, 2),
            "gi_out": round(vol_gi_out, 2),
            "overall_yield_pct": round(vol_gi_out / volume * 100, 2) if volume > 0 else 0,
        },
        "costs": {
            "rm_total": round(rm_total, 2),
            "pk":  pk_cost,
            "cr":  cr_cost,
            "gi":  gi_cost,
            "depreciation": round(depre, 2),
            "total_cost": round(total_cost, 2),
            "sga": round(sga_cost, 2),
            "cogs": round(cogs, 2),
        },
        "unit_cost_thb_per_t": unit_cost,
        "gic_map": round(gic_map, 2),
        "pnl": {
            "revenue":      round(revenue, 2),
            "gross_profit": round(gross_profit, 2),
            "ebit":         round(ebit, 2),
            "tax":          round(tax, 2),
            "net_income":   round(net_income, 2),
            "gross_margin_pct": round(gross_profit / revenue * 100, 2) if revenue > 0 else 0,
            "net_margin_pct":   round(net_income / revenue * 100, 2) if revenue > 0 else 0,
        },
    }


# ── Pipe Plants (1100 / 1200) ─────────────────────────────────────────────────

def calc_pipe_simulation(plant: str, state: dict) -> dict:
    """
    Pipe A1 (Plant 1100) or Pipe A2 (Plant 1200) simulation.

    plant: '1100' or '1200'
    state: full Zustand store state (uses p1100* or p1200* fields)
    """
    p = plant  # '1100' or '1200'

    volume   = float(state.get(f"p{p}Volume", 0))
    slit_yield = float(state.get(f"p{p}SlitYield", 100)) / 100
    pipe_yield = float(state.get(f"p{p}PipeYield", 100)) / 100

    vol_slit_out = volume * slit_yield
    vol_pipe_out = vol_slit_out * pipe_yield

    slit_cost = calc_process_cost(state.get(f"p{p}SlittingItems", []), vol_slit_out)
    pipe_cost = calc_process_cost(state.get(f"p{p}FormingItems", []), vol_pipe_out)

    # RM source
    rm_source = state.get(f"p{p}RmSource", "internal")
    if rm_source == "external":
        rm_price_per_t = float(state.get(f"p{p}ExternalRmPrice", 0))
    else:
        # Use GIC MAP derived from GI plant state
        rm_price_per_t = float(state.get("gicMAP", 0))  # caller should pass this in

    rm_total = rm_price_per_t * volume

    # C-Channel (Plant 1200 only)
    cc_result = None
    if p == "1200":
        cc_yield  = float(state.get("p1200CcYield", 100)) / 100
        pipe_mt   = float(state.get("p1200PipeMt", vol_pipe_out))
        cc_mt     = vol_pipe_out - pipe_mt
        cc_cost   = calc_process_cost(state.get("p1200CcItems", []), cc_mt * cc_yield)
        cc_result = {
            "cc_mt": round(cc_mt, 2),
            "cc_cost": cc_cost,
        }

    total_cost = rm_total + slit_cost["total"] + pipe_cost["total"]
    if cc_result:
        total_cost += cc_result["cc_cost"]["total"]

    unit_cost = round(total_cost / vol_pipe_out, 2) if vol_pipe_out > 0 else 0.0

    result = {
        "plant": p,
        "volumes": {
            "input": round(volume, 2),
            "slit_out": round(vol_slit_out, 2),
            "pipe_out": round(vol_pipe_out, 2),
            "overall_yield_pct": round(vol_pipe_out / volume * 100, 2) if volume > 0 else 0,
        },
        "costs": {
            "rm_source": rm_source,
            "rm_price_per_t": round(rm_price_per_t, 2),
            "rm_total": round(rm_total, 2),
            "slitting": slit_cost,
            "forming": pipe_cost,
            "total_cost": round(total_cost, 2),
        },
        "unit_cost_thb_per_t": unit_cost,
    }
    if cc_result:
        result["c_channel"] = cc_result

    return result


# ── RM Forecast ───────────────────────────────────────────────────────────────

def calc_rm_forecast(state: dict, months: int = 12) -> dict:
    """
    RM FIFO MAP forecast for all materials.
    Returns per-material month-by-month price forecast.
    """
    materials  = ["HRC", "ZINC", "GIC", "WIRE"]
    layers_map = state.get("rmStockLayers", {})
    cons_map   = state.get("rmMonthlyConsumption", {})

    forecasts = {}
    for mat in materials:
        layers      = layers_map.get(mat, [])
        consumption = float(cons_map.get(mat, 0))
        if layers and consumption > 0:
            forecasts[mat] = forecast_map(layers, consumption, months)
        else:
            forecasts[mat] = []

    # GIC MAP from GI simulation (if state has full GI data)
    gic_map = 0.0
    if state.get("volume") and state.get("pkItems"):
        try:
            gi_result = calc_gi_simulation(state)
            gic_map = gi_result["gic_map"]
        except Exception:
            pass

    return {
        "gic_map": round(gic_map, 2),
        "forecasts": forecasts,
        "months": months,
    }
