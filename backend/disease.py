"""Leaf-disease classifier: the team's trained Verdex model, loaded if available.

Uses the PyTorch checkpoints from farming_robot/ (timm backbone, saved as
{"model", "class_names", "backbone", "size"}). Preprocessing matches
tools/train_torch.py exactly. The energy score lets the model say "not a leaf
I know" instead of guessing.

Torch is optional: without it the app still runs, and the robot panel offers
labelled sample detections instead of live classification.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

ROBOT_DIR = Path(os.environ.get(
    "VERDEX_MODEL_DIR",
    Path(__file__).resolve().parent.parent.parent / "farming_robot" / "farming_robot"))
MODEL_FILE = os.environ.get("VERDEX_MODEL", "v2_deit3.pt")

_model = None
_info: dict = {"loaded": False, "reason": "not tried"}


def load() -> dict:
    global _model, _info
    if _model is not None or _info["reason"] != "not tried":
        return _info
    path = ROBOT_DIR / MODEL_FILE
    try:
        import timm
        import torch
        if not path.exists():
            raise FileNotFoundError(path)
        ckpt = torch.load(path, map_location="cpu", weights_only=False)
        model = timm.create_model(ckpt["backbone"], pretrained=False,
                                  num_classes=len(ckpt["class_names"]))
        model.load_state_dict(ckpt["model"])
        model.eval()
        calib = ROBOT_DIR / (Path(MODEL_FILE).stem + ".calib.json")
        threshold = json.loads(calib.read_text())["energy_threshold"] if calib.exists() else None
        _model = model
        _info = dict(loaded=True, file=path.name, backbone=ckpt["backbone"], size=ckpt["size"],
                     class_names=ckpt["class_names"], energy_threshold=threshold, reason="ok")
    except Exception as exc:  # torch missing, file missing, etc.
        _info = dict(loaded=False, reason=f"{type(exc).__name__}: {exc}")
    return _info


def classify(image_bytes: bytes) -> dict:
    info = load()
    if not info["loaded"]:
        raise RuntimeError(info["reason"])
    import torch
    import torchvision.transforms as T
    from PIL import Image

    size = info["size"]
    tf = T.Compose([T.Resize(int(size * 1.14)), T.CenterCrop(size), T.ToTensor(),
                    T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])])
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    x = tf(img).unsqueeze(0)
    with torch.no_grad():
        logits = _model(x)[0]
    probs = torch.softmax(logits, -1)
    energy = float(-torch.logsumexp(logits, -1))
    top = torch.topk(probs, 3)
    names = info["class_names"]
    thr = info["energy_threshold"]
    known = True if thr is None else energy <= thr
    return dict(
        label=names[int(top.indices[0])], confidence=float(top.values[0]),
        top3=[dict(label=names[int(i)], p=float(p)) for p, i in zip(top.values, top.indices)],
        energy=round(energy, 2), known=known,
    )
