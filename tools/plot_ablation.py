"""Generate learning-curve and test-metric comparison chart."""
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RPT = ROOT / "reports"

eff_hist = json.loads((RPT / "history.json").read_text())
scr_hist = json.loads((RPT / "scratch_history.json").read_text())
comp = json.loads((RPT / "model_comparison.json").read_text())

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.3), dpi=160)
ax1.plot([h["epoch"] for h in scr_hist], [h["val_acc"] * 100 for h in scr_hist],
         marker="o", linewidth=2, color="#d97706", label="SmallCNN (from scratch)")
ax1.plot([h["epoch"] for h in eff_hist], [h["val_acc"] * 100 for h in eff_hist],
         marker="s", linewidth=2, color="#15803d", label="EfficientNet-B0 (ImageNet transfer)")
ax1.set_title("Validation Accuracy vs. Epoch")
ax1.set_xlabel("Epoch"); ax1.set_ylabel("Validation Accuracy (%)")
ax1.grid(True, linestyle="--", alpha=0.35); ax1.legend(frameon=True)

labels = list(comp.keys())
x = np.arange(len(labels)); w = 0.26
ax2.bar(x - w, [comp[k]["all_test"]["top1_acc"] * 100 for k in labels], width=w, label="Top-1 Acc", color="#15803d")
ax2.bar(x, [comp[k]["all_test"]["top5_acc"] * 100 for k in labels], width=w, label="Top-5 Acc", color="#0284c7")
ax2.bar(x + w, [comp[k]["all_test"]["macro_f1"] * 100 for k in labels], width=w, label="Macro-F1", color="#6d28d9")
ax2.set_xticks(x); ax2.set_xticklabels(labels, rotation=10, ha="right"); ax2.set_ylim(0, 108)
ax2.set_ylabel("Score (%)"); ax2.set_title("Held-Out Test Set Ablation")
ax2.grid(True, axis="y", linestyle="--", alpha=0.35); ax2.legend(frameon=True)

plt.tight_layout()
out = RPT / "fig_ablation_scratch_vs_transfer.png"
plt.savefig(out)
print(f"Saved {out.resolve()}")
