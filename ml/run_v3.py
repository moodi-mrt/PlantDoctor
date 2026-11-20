"""v3 pipeline driver: dataset audit + grouped split -> architecture comparison -> full training.

    nohup .venv/bin/python ml/run_v3.py > data/logs/run_v3.log 2>&1 &

Comparison: every candidate trains on the SAME split with the same budget (150 imgs/class, 3 epochs)
and is scored on validation-free data (test macro-F1 and external field accuracy). Candidates whose
CPU latency exceeds 300 ms are not eligible (deployment target is a CPU server).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "bin" / "python")
OUT = ROOT / "reports" / "v3"
CANDIDATES = [("mobilenet_v3_large", 224), ("efficientnet_b0", 224), ("efficientnet_b2", 260), ("convnext_tiny", 224)]


def run(args):
    print(">>", " ".join(args), flush=True)
    p = subprocess.Popen([PY, *args], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    result = None
    for line in p.stdout:
        print(line, end="", flush=True)
        if line.startswith("RESULT "):
            result = json.loads(line[7:])
    if p.wait() != 0:
        raise SystemExit(f"failed: {args}")
    return result


def main():
    if not (OUT / "split.json").exists() or "--resplit" in sys.argv:
        run(["ml/prepare_split.py"])
    comp_p = OUT / "arch_comparison.json"
    comp = json.loads(comp_p.read_text()) if comp_p.exists() else {}
    for arch, size in CANDIDATES:
        key = f"{arch}@{size}"
        if key in comp:
            continue
        r = run(["ml/train_disease.py", "--arch", arch, "--size", str(size), "--epochs", "3", "--subset", "150",
                 "--patience", "9", "--tag", "cmp", "--batch", "32" if arch in ("efficientnet_b2", "convnext_tiny") else "48"])
        comp[key] = r
        comp_p.write_text(json.dumps(comp, indent=1))
    def score(r):
        return 0.5 * r["macro_f1"] + 0.5 * ((r.get("field") or {}).get("accuracy") or 0)
    eligible = {k: v for k, v in comp.items() if (v.get("latency_ms_cpu") or 1e9) <= 300}
    best = max(eligible, key=lambda k: score(eligible[k]))
    comp["_selection"] = {"rule": "max 0.5*test_macro_F1 + 0.5*field_accuracy, CPU latency <= 300 ms",
                          "scores": {k: round(score(v), 4) for k, v in comp.items() if not k.startswith("_")},
                          "selected": best, "time": time.strftime("%Y-%m-%d %H:%M")}
    comp_p.write_text(json.dumps(comp, indent=1))
    print("SELECTED", best, flush=True)
    arch, size = best.split("@")
    run(["ml/train_disease.py", "--arch", arch, "--size", size, "--epochs", "12", "--epoch-size", "40000",
         "--patience", "3", "--tag", "full", "--batch", "32" if arch in ("efficientnet_b2", "convnext_tiny") else "48"])


if __name__ == "__main__":
    main()
