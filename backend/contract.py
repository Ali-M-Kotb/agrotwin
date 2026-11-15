"""Adapter: our simulate() result → the frozen AgroTwin v1 result contract.

The v1 contracts (contracts/v1/*.schema.json) were designed in Yaseen Abdelal's AgroTwin
repository (github.com/Yaseen-Saad/AgroTwin). The engine here works per feddan; the contract
is per hectare (1 feddan = 0.42 ha), water in mm (1 mm over a feddan = 4.2 m³).
GET /api/v1/result emits it; tests validate it against the schema.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

import config
from crops import FEDDAN_HA, MM_TO_M3_PER_FEDDAN

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "contracts" / "v1" / "result.schema.json").read_text())
VERSION = (ROOT / "VERSION").read_text().strip() if (ROOT / "VERSION").exists() else "0.0.0"

def _per_ha(x):
    return round(x / FEDDAN_HA, 2)

def _rng(m: dict, f=lambda v: v, unit=None, currency=None) -> dict:
    out = dict(p10=round(f(m["p10"]), 2), median=round(f(m["median"]), 2), p90=round(f(m["p90"]), 2),
               source=str(m.get("source", "computed")).split(":")[0] if str(m.get("source", "")).startswith("computed") else m.get("source", "computed"))
    if unit:
        out["unit"] = unit
    if currency:
        out["currency"] = currency
    return out

def to_v1(res: dict, lang: str = "en") -> dict:
    rots = []
    for r in res["rotations"]:
        n = len(r["years"])
        mm = lambda m3: m3 / MM_TO_M3_PER_FEDDAN
        t = r["text"]
        rots.append(dict(
            rotation_id=r["rotation_id"], label=r["label"][lang],
            metrics=dict(
                water_use_mm=_rng(r["water_m3"], mm, unit="mm/yr (gross irrigation)"),
                deficit_days=dict(p10=r["deficit_days"]["median"], median=r["deficit_days"]["median"],
                                  p90=r["deficit_days"]["median"], unit="days / 3 yr", source="computed"),
                bare_days=dict(p10=r["bare_days"]["median"], median=r["bare_days"]["median"],
                               p90=r["bare_days"]["median"], unit="days / 3 yr", source="computed"),
                erosion_index=dict(p10=r["erosion_index"]["median"], median=r["erosion_index"]["median"],
                                   p90=r["erosion_index"]["median"], unit="mm", source="computed"),
                n_credit_kg_ha=dict(low=_per_ha(r["n_credit_kg_fed"]["low"]), high=_per_ha(r["n_credit_kg_fed"]["high"]),
                                    unit="kg N/ha", source=r["n_credit_kg_fed"]["source"]),
                profit_per_ha=_rng(r["profit"], _per_ha, currency="EGP"),
                loss_year_share=dict(value=r["loss_year_share"]["value"], source="computed"),
            ),
            evidence=[x[lang] for x in t["evidence"]], benefits=[x[lang] for x in t["benefits"]],
            gaps=[x[lang] for x in t["gaps"]], review_flags=[x[lang] for x in t["review"]],
            barcode=[dict(year=b["year"], profit_per_ha=_per_ha(b["profit"]), **{"class": b["cls"]}, source="computed")
                     for b in r["barcode"]],
            worst_year=dict(year=r["worst_year"]["year"], profit_per_ha=_per_ha(r["worst_year"]["profit"]),
                            currency="EGP", source="computed"),
            loss_year_share=dict(value=r["loss_year_share"]["value"], source="computed"),
            excluded=dict(is_excluded=r["excluded"]["is_excluded"],
                          reasons=[f"{x['kind']}" for x in r["excluded"]["reasons"]]),
        ))
    f = res.get("fusion") or {}
    used = bool(f.get("used"))
    rw = f.get("range_width") or {}
    w = res.get("weights", {})
    tot = sum(float(w.get(k, 0)) for k in ("water", "soil", "profit", "risk")) or 1
    sc = res.get("scout_summary", {})
    return dict(
        schema_version="1.0.0", version=VERSION, site_id=res["site"]["id"],
        generated_by=f"agrotwin engine {VERSION} (AI-assisted code, computed at request time)",
        mode=res["mode"] if res["mode"] in ("LIVE", "REPLAY", "SIMULATED", "NONE") else "SIMULATED",
        scenario=dict(rain_mult=res["scenario"]["rain_mult"], temp_offset_c=res["scenario"]["temp_offset_c"],
                      price_mult=res["scenario"]["price_mult"]),
        years=res["years"], rotations=rots,
        fusion=dict(
            used=used, scout_run_ids=f.get("scout_run_ids", []) if used else [], n_points=int(f.get("n_points", 0) or 0),
            weights_by_year={str(k): v for k, v in (f.get("weights_by_year") or {}).items()},
            ess=float(f.get("ess", len(res["years"])) or 0), sigma_used=float(f.get("sigma_used", 0) or 0),
            range_width=dict(without_scout=_per_ha(rw.get("without_scout", 0) or 0), with_scout=_per_ha(rw.get("with_scout", 0) or 0),
                             unit="EGP/ha (this season)", source="computed"),
            confidence_label=f.get("confidence_label", "low"),
            bias_check=dict(n_overlap_days=0, mean_gap=None, applied=False),
            notes=["Scout readings re-weight this season only; 3-year ranges stay on history."],
        ),
        scout_summary=dict(sightings=dict(healthy=sc.get("counts", {}).get("healthy", 0),
                                          diseased=sc.get("counts", {}).get("diseased", 0),
                                          unknown=sc.get("counts", {}).get("unknown", 0)),
                           model=str(sc.get("model", "v2_deit3")), note=sc.get("note", "Sightings are observations, not diagnoses.")),
        ranking=dict(weights=dict(water=float(w.get("water", 0)) / tot, soil=float(w.get("soil", 0)) / tot,
                                  profit=(float(w.get("profit", 0)) + float(w.get("risk", 0))) / tot),
                     order=res["order"], tie_band_applied=bool(res["no_clear_winner"]),
                     notes=["Min-max across the replayed candidate pool; 'risk' (worst years) is folded into 'profit' for v1."]),
        assumptions=[dict(id=a["name"], description=a["meaning"],
                          value=a["value"] if isinstance(a["value"], (str, int, float, bool)) or a["value"] is None else json.dumps(a["value"]),
                          source=a["source"], editable=True) for a in config.table()],
    )

def validate(doc: dict) -> list[str]:
    return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(doc)]
