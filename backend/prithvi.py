"""Prithvi-EO-2.0 (NASA–IBM geospatial foundation model) inside AgroTwin.

AI-generated (Claude, Anthropic) under human review — see docs/AI_USE.md.

Prithvi-EO-2.0-300M-TL is a 300 M-parameter vision transformer pre-trained by NASA and IBM on NASA's Harmonized
Landsat-Sentinel-2 (HLS) imagery, with time and location encodings (Apache-2.0,
huggingface.co/ibm-nasa-geospatial/Prithvi-EO-2.0-300M-TL). Weights (1.33 GB) live in data/models/prithvi/ (git-ignored).

What AgroTwin uses it for
    A crop-type / cropping-pattern detector: a field's multi-date HLS chips (6 bands × up to 4 dates, 224 × 224 px at 30 m)
    → Prithvi embeddings → a small classifier head trained on labelled fields (the consent-based outcome log, /api/outcomes).
    Detected history replaces "tell us what you grew" in Plan Mode and the time machine.

Status (honest)
    - Encoder: downloaded and verified to run (scripts/prithvi_check.py).
    - HLS imagery: not downloaded yet (needs an Earthdata login and several GB; waiting for the team's go-ahead).
    - Classifier head: not trained (needs labelled fields). The API says so instead of guessing.
"""
from __future__ import annotations

import json
import pickle
import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "models" / "prithvi"
WEIGHTS = DIR / "Prithvi_EO_V2_300M_TL.pt"
HEAD = Path(__file__).resolve().parent / "models" / "crop_head.pkl"
_lock = threading.Lock()
_model = {}


def config() -> dict:
    return json.loads((DIR / "config.json").read_text())["pretrained_cfg"]


def status() -> dict:
    ok = WEIGHTS.exists() and WEIGHTS.stat().st_size > 1e9
    return dict(model="Prithvi-EO-2.0-300M-TL (NASA–IBM, Apache-2.0)", weights_present=ok,
                weights_mb=round(WEIGHTS.stat().st_size / 1e6, 1) if WEIGHTS.exists() else 0,
                hls_imagery="not downloaded (pending the team's approval; needs an Earthdata login)",
                crop_head="trained" if HEAD.exists() else "not trained (needs labelled fields from the outcome log)",
                bands=config()["bands"] if (DIR / "config.json").exists() else None)


def load(num_frames: int = 4):
    """Encoder only (decoder dropped to save memory). Cached per frame count."""
    with _lock:
        if num_frames in _model:
            return _model[num_frames]
        import torch
        sys.path.insert(0, str(DIR))
        from prithvi_mae import PrithviMAE
        cfg = dict(config())
        for k in ("bands", "mean", "std", "origin_url", "paper_ids"):
            cfg.pop(k, None)
        cfg.update(num_frames=num_frames, in_chans=6, coords_encoding=["time", "location"])
        m = PrithviMAE(**cfg)
        sd = torch.load(WEIGHTS, map_location="cpu", weights_only=True)
        sd = {k: v for k, v in sd.items() if "pos_embed" not in k}
        missing, unexpected = m.load_state_dict(sd, strict=False)
        enc = m.encoder.eval()
        del m
        _model[num_frames] = (enc, [k for k in missing if k.startswith("encoder.") and "pos_embed" not in k])
        return _model[num_frames]


def embed(chips: np.ndarray, dates: list[tuple[int, int]], lat: float, lon: float) -> dict:
    """chips: (T, 6, H, W) HLS surface reflectance (scaled integers, bands B02,B03,B04,B05,B06,B07), H = W = 224.
    dates: [(year, day_of_year)] per frame. Returns the pooled 1,024-d field embedding and the per-patch grid."""
    import torch
    cfg = config()
    T = chips.shape[0]
    enc, _ = load(T)
    mean = np.asarray(cfg["mean"], np.float32)[None, :, None, None]
    std = np.asarray(cfg["std"], np.float32)[None, :, None, None]
    x = np.where(chips == -9999, 0.0, (chips.astype(np.float32) - mean) / std)
    x = torch.from_numpy(np.moveaxis(x, 0, 1)[None])                       # (1, C, T, H, W)
    tc = torch.tensor([[list(d) for d in dates]], dtype=torch.float32)       # (1, T, 2)
    lc = torch.tensor([[lat, lon]], dtype=torch.float32)                     # (1, 2)
    t0 = time.time()
    with torch.no_grad():
        feats = enc.forward_features(x, tc, lc)
    last = feats[-1][0, 1:, :].numpy()                                       # tokens without CLS
    return dict(embedding=last.mean(0), patches=last, tokens=last.shape[0], seconds=round(time.time() - t0, 2))


def train_head(embeddings: np.ndarray, labels: list[str]) -> dict:
    """Fit the crop-type head on labelled field embeddings (logistic regression; small data friendly)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_score
    clf = LogisticRegression(max_iter=2000, C=0.5)
    cv = cross_val_score(clf, embeddings, labels, cv=min(5, max(2, len(set(labels))))) if len(labels) >= 20 else None
    clf.fit(embeddings, labels)
    with open(HEAD, "wb") as f:
        pickle.dump(dict(clf=clf, classes=sorted(set(labels)), n=len(labels), cv=None if cv is None else float(cv.mean())), f)
    return dict(n=len(labels), classes=sorted(set(labels)), cv_accuracy=None if cv is None else float(cv.mean()))


def detect(embedding: np.ndarray) -> dict:
    if not HEAD.exists():
        return dict(available=False, reason="crop head not trained yet: needs labelled fields (outcome log) and HLS imagery")
    h = pickle.load(open(HEAD, "rb"))
    p = h["clf"].predict_proba(embedding[None])[0]
    order = np.argsort(-p)
    return dict(available=True, crop=h["clf"].classes_[order[0]], probability=float(p[order[0]]),
                alternatives=[(h["clf"].classes_[i], float(p[i])) for i in order[1:3]], trained_on=h["n"], cv_accuracy=h["cv"])
