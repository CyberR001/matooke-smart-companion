#!/usr/bin/env python3
"""Fine-tuning scaffold for the 5.1 image model (NOT wired into the app).

Section 5.1 of the concept proposal defers computer vision until the team has a
properly labelled banana/matooke image set and expert review. This script is the
plan made executable: it will train a MobileNetV3-small transfer-learning model
on a folder-per-class dataset, report honest per-class metrics, and refuse to
produce a model card that hides weak classes.

Deliberately not imported by `app` - the shipped product uses the guided
symptom questionnaire, and this file must not make the app depend on torch.

    pip install torch torchvision
    python ml/train_matooke_vision.py --data ml/data --epochs 12

Expected layout:

    ml/data/
      bxw/            img001.jpg ...
      black_sigatoka/ ...
      healthy/        ...

Class folder names should match keys in app/engine/knowledge/matooke_diseases.json
so a later release can merge image and symptom evidence into one ranking.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

MIN_IMAGES_PER_CLASS = 60


def die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def check_data(root: Path) -> dict[str, list[Path]]:
    classes: dict[str, list[Path]] = {}
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        files = [p for p in sub.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
        if files:
            classes[sub.name] = files
    return classes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("ml/data"))
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--lr-head", type=float, default=3e-4)
    ap.add_argument("--lr-backbone", type=float, default=1e-5)
    ap.add_argument("--freeze-backbone-for", type=int, default=2, help="epochs to train only the head")
    ap.add_argument("--out", type=Path, default=Path("ml/artifacts"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--force", action="store_true", help="proceed even if a class is thin on images")
    args = ap.parse_args()

    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader
        from torchvision import models, transforms
        from torchvision.datasets import ImageFolder
    except ImportError:
        die(
            "torch/torchvision are not installed, and this script intentionally does not\n"
            "affect the app. To continue:\n\n    pip install torch torchvision\n\n"
            "The shipped prototype answers from the guided questionnaire in\n"
            "app/engine/diseases.py; no image model is required for that."
        )

    if not args.data.exists():
        die(f"No dataset at {args.data}. See ml/README.md for the collection protocol.")

    classes = check_data(args.data)
    if not classes:
        die(f"No class folders with images under {args.data}")
    thin = {k: len(v) for k, v in classes.items() if len(v) < MIN_IMAGES_PER_CLASS}
    if thin and not args.force:
        die(
            "Too few images for a trustworthy model: "
            f"{thin} (need >= {MIN_IMAGES_PER_CLASS} each).\n"
            "Field collection is the bottleneck, not the architecture. Collect more, or run\n"
            "with --force only for a pipeline smoke test - never for a reported accuracy."
        )

    torch.manual_seed(args.seed)
    n = sum(len(v) for v in classes.values())
    val_n = max(int(n * 0.2), len(classes) * 10)
    train_tf = transforms.Compose(
        [
            transforms.RandomResizedCrop(args.size, scale=(0.7, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(0.2, 0.2, 0.2, 0.05),  # leaf colour varies with sun and ripeness
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )
    val_tf = transforms.Compose(
        [
            transforms.Resize(int(args.size * 1.08)),
            transforms.CenterCrop(args.size),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    full = ImageFolder(args.data, transform=train_tf)
    names = full.classes
    # Deterministic stratified split by folder index, no extra dependency.
    by_class: dict[int, list[int]] = {i: [] for i in range(len(names))}
    for idx, (_p, target) in enumerate(full.samples):
        by_class[target].append(idx)
    train_idx: list[int] = []
    val_idx: list[int] = []
    for _cls, idxs in by_class.items():
        idxs = sorted(idxs)
        k = max(1, round(len(idxs) * 0.2))
        val_idx.extend(idxs[:k])
        train_idx.extend(idxs[k:])

    train_ds = ImageFolder(args.data, transform=train_tf)
    val_ds = ImageFolder(args.data, transform=val_tf)
    train_ds.samples = [full.samples[i] for i in train_idx]
    val_ds.samples = [full.samples[i] for i in val_idx]
    train_ds.targets = [full.targets[i] for i in train_idx]
    val_ds.targets = [full.targets[i] for i in val_idx]
    if val_n and not val_ds.samples:
        die("Validation split is empty - each class needs at least 2 images.")

    loader_train = DataLoader(
        train_ds, batch_size=args.batch_size, shuffle=True, num_workers=2, pin_memory=True
    )
    loader_val = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, num_workers=2, pin_memory=True)

    weights = models.MobileNet_V3_Small_Weights.DEFAULT
    model = models.mobilenet_v3_small(weights=weights)
    model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, len(names))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)

    for p in model.features.parameters():
        p.requires_grad = False
    optimizer = torch.optim.AdamW(
        [{"params": model.classifier.parameters(), "lr": args.lr_head}], weight_decay=1e-4
    )
    lossf = nn.CrossEntropyLoss()

    print(f"classes={names}\ntrain={len(train_ds.samples)} val={len(val_ds.samples)} device={device}")
    for epoch in range(args.epochs):
        if epoch == args.freeze_backbone_for:
            for p in model.features.parameters():
                p.requires_grad = True
            optimizer = torch.optim.AdamW(
                [
                    {"params": model.classifier.parameters(), "lr": args.lr_head},
                    {"params": model.features.parameters(), "lr": args.lr_backbone},
                ],
                weight_decay=1e-4,
            )
            print(f"epoch {epoch}: unfreezing backbone, lower lr")

        model.train()
        run_loss = 0.0
        for x, y in loader_train:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            loss = lossf(model(x), y)
            loss.backward()
            optimizer.step()
            run_loss += float(loss) * x.size(0)
        print(f"epoch {epoch + 1:2d}/{args.epochs} train loss {run_loss / max(len(train_ds.samples), 1):.4f}")

    model.eval()
    correct = 0
    per_class = {c: {"tp": 0, "fp": 0, "fn": 0} for c in names}
    with torch.no_grad():
        for x, y in loader_val:
            logits = model(x.to(device))
            pred = logits.argmax(1).cpu()
            correct += int((pred == y).sum())
            for t, p in zip(y.tolist(), pred.tolist(), strict=True):
                if t == p:
                    per_class[names[t]]["tp"] += 1
                else:
                    per_class[names[t]]["fn"] += 1
                    per_class[names[p]]["fp"] += 1
    acc = correct / max(len(val_ds.samples), 1)

    report = {
        "trained_on": str(args.data),
        "date": date.today().isoformat(),
        "architecture": "MobileNetV3-small, ImageNet weights, fine-tuned head then backbone",
        "image_size": args.size,
        "epochs": args.epochs,
        "val_accuracy": round(acc, 4),
        "n_train": len(train_ds.samples),
        "n_val": len(val_ds.samples),
        "per_class": {
            k: {
                "precision": round(v["tp"] / (v["tp"] + v["fp"]), 3) if v["tp"] + v["fp"] else None,
                "recall": round(v["tp"] / (v["tp"] + v["fn"]), 3) if v["tp"] + v["fn"] else None,
                "support": v["tp"] + v["fn"],
            }
            for k, v in per_class.items()
        },
        "classes": names,
        "limitations": [
            "No probability calibration has been performed, so softmax values are not confidence.",
            "Field images differ from research photos in lighting, angle and ripeness.",
            "A weak class must fall back to the symptom questionnaire and referral path.",
            "Output is a possible condition, never a diagnosis.",
        ],
        "deployment_note": (
            "Before this can answer anything in the app it needs: expert-verified labels, a held-out "
            "test set from different gardens, calibration, a confidence floor with referral, and a "
            "review by an agricultural officer."
        ),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": model.state_dict(), "classes": names, "report": report}, args.out / "model.pt")
    (args.out / "model_card.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2)[:1500])
    print(f"\nsaved -> {args.out / 'model.pt'} and model_card.json")
    if acc < 0.75 or any((v.get("recall") or 0) < 0.6 for v in report["per_class"].values()):
        print(
            "\nRefusing to call this usable: accuracy or a class recall is too low. "
            "Keep the questionnaire path as the answer and treat this as research only.",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
