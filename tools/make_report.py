"""Build reports/PlantDoctor_Report.pdf from the saved metrics and figures."""
import json
import platform
from datetime import date
from pathlib import Path

import torch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "reports"; F = R / "figures"
NOTO = Path("/usr/share/fonts/truetype/noto")
for name, file in [("Sans", "NotoSans-Regular"), ("Sans-B", "NotoSans-Bold"), ("Sans-I", "NotoSans-Italic"),
                   ("Serif", "NotoSerif-Regular"), ("Serif-B", "NotoSerif-Bold")]:
    pdfmetrics.registerFont(TTFont(name, str(NOTO / f"{file}.ttf")))
pdfmetrics.registerFontFamily("Sans", normal="Sans", bold="Sans-B", italic="Sans-I", boldItalic="Sans-B")

INK, INK2, INK3 = colors.HexColor("#17201a"), colors.HexColor("#4b554e"), colors.HexColor("#848c86")
BRAND, SOFT, LINE = colors.HexColor("#1f4d2f"), colors.HexColor("#eef3eb"), colors.HexColor("#dcdbd3")
WARN_BG, BAD_BG = colors.HexColor("#fbf0da"), colors.HexColor("#f9e5e0")

S = {
    "body": ParagraphStyle("body", fontName="Sans", fontSize=9.6, leading=14.6, textColor=INK, spaceAfter=7),
    "small": ParagraphStyle("small", fontName="Sans", fontSize=8.2, leading=11.5, textColor=INK2),
    "cap": ParagraphStyle("cap", fontName="Sans-I", fontSize=8, leading=11, textColor=INK3, spaceBefore=3, spaceAfter=12),
    "h1": ParagraphStyle("h1", fontName="Serif-B", fontSize=17, leading=22, textColor=INK, spaceBefore=6, spaceAfter=10),
    "h2": ParagraphStyle("h2", fontName="Sans-B", fontSize=10.5, leading=14, textColor=BRAND, spaceBefore=12, spaceAfter=5),
    "kick": ParagraphStyle("kick", fontName="Sans-B", fontSize=8, leading=10, textColor=BRAND, spaceAfter=4),
    "bul": ParagraphStyle("bul", fontName="Sans", fontSize=9.6, leading=14.2, textColor=INK, leftIndent=12, bulletIndent=2, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Sans", fontSize=8.5, leading=11.6, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Sans-B", fontSize=8.5, leading=11.6, textColor=INK),
    "title": ParagraphStyle("title", fontName="Serif-B", fontSize=30, leading=36, textColor=INK, alignment=TA_LEFT),
}
P = lambda t, s="body": Paragraph(t, S[s])
B = lambda items: [Paragraph(i, S["bul"], bulletText="•") for i in items]
W = A4[0] - 36 * mm


def fig(name, caption, width=W):
    from PIL import Image as PI
    w, h = PI.open(F / name).size
    return KeepTogether([Image(str(F / name), width=width, height=width * h / w), P(caption, "cap")])


def table(rows, widths, header=True, zebra=True):
    data = [[Paragraph(str(c), S["cellb" if header and i == 0 else "cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
          ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
          ("LINEBELOW", (0, 0), (-1, -1), .4, LINE)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("LINEBELOW", (0, 0), (-1, 0), .8, BRAND)]
    t.setStyle(TableStyle(st))
    return t


def callout(text, bg=SOFT):
    t = Table([[Paragraph(text, S["body"])]], colWidths=[W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LEFTPADDING", (0, 0), (-1, -1), 12),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 9),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LINEBEFORE", (0, 0), (0, -1), 2.5, BRAND)]))
    return t


def deco(c, doc):
    c.saveState()
    c.setFont("Sans", 7.5); c.setFillColor(INK3)
    if doc.page > 1:
        c.drawString(18 * mm, 12 * mm, "PlantDoctor — technical report")
        c.drawRightString(A4[0] - 18 * mm, 12 * mm, str(doc.page))
        c.setStrokeColor(LINE); c.setLineWidth(.5); c.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    c.restoreState()


def main():
    t = json.load(open(R / "test_metrics.json")); f = json.load(open(R / "field_metrics.json"))
    h = json.load(open(R / "history.json")); sp = json.load(open(R / "split.json"))
    pct = lambda x: f"{x * 100:.1f}%"
    pc = t["per_class"]
    worst = sorted(pc.items(), key=lambda kv: kv[1]["f1"])[:6]
    pretty = lambda c: c.replace("___", " – ").replace("_", " ").replace(",", "")
    n_train, n_val, n_test = len(sp["train"]), len(sp["val"]), len(sp["test"])
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    field_best = sorted(f["per_class"].items(), key=lambda kv: -kv[1]["top1"])
    field_worst = [k for k, v in field_best if v["top1"] == 0]

    st = []
    # ---------------- Cover
    st += [Spacer(1, 52 * mm), P("TECHNICAL REPORT", "kick"), P("PlantDoctor", "title"), Spacer(1, 4),
           P("Crop and plant disease detection from leaf photos: tools used, how the model was trained, "
             "and an honest account of when it works and when it does not.", "body"), Spacer(1, 14 * mm)]
    st.append(table([
        ["Headline result", ""],
        ["Lab-style photos (PlantVillage test set)", f"<b>{pct(t['test_acc'])}</b> exact-class accuracy · macro-F1 {t['macro_f1']:.3f}"],
        ["Real field photos (PlantDoc, independent)", f"<b>{pct(f['top1_acc'])}</b> exact-class · {pct(f['top5_acc'])} in top-5 · {pct(f['crop_acc'])} correct crop"],
        ["Classes", f"{len(sp['classes'])} (38 crop/disease classes across 14 crops + 1 'no leaf' class)"],
        ["Model", "EfficientNet-B0 (5.3 M parameters), ImageNet pre-trained, fine-tuned"],
        ["Hardware", f"{gpu} (4 GB) · {platform.system()} · PyTorch {torch.__version__.split('+')[0]}"],
        ["Date", date.today().strftime("%d %B %Y")],
    ], [62 * mm, W - 62 * mm]))
    st.append(PageBreak())

    # ---------------- 1. Summary
    st += [P("1. Summary", "h1"),
           P(f"PlantDoctor is a local web application: you open it in a browser, drop in a photo of a leaf, and it returns the crop, the most likely disease, "
             f"a confidence score, practical next steps and a heatmap of the leaf regions that drove the decision. "
             f"The model is a convolutional neural network fine-tuned on the public <b>PlantVillage</b> dataset (54,305 images)."),
           P(f"On held-out PlantVillage images the model is correct <b>{pct(t['test_acc'])}</b> of the time. That number is real but it is "
             f"<b>not</b> what a farmer should expect in a field. When the same model is tested on <b>{f['n_images']}</b> real-world photos from a different "
             f"dataset (PlantDoc), exact-class accuracy falls to <b>{pct(f['top1_acc'])}</b>. Section 6 explains why: PlantVillage photos are "
             f"single leaves on a plain grey board under controlled light, so the model learns a narrow visual world."),
           callout(f"<b>Bottom line.</b> Reliable as a screening tool for clear, single-leaf photos taken against a plain background. "
                   f"Not reliable on cluttered field scenes without more diverse training data. The app's confidence gate is the main safeguard: "
                   f"on field photos it flagged <b>{pct(f['share_flagged_low_conf'])}</b> of images as uncertain, and predictions it was confident about were right "
                   f"<b>{pct(f['acc_when_confident'])}</b> of the time versus <b>{pct(f['acc_when_flagged'])}</b> for flagged ones.")]

    # ---------------- 2. Environment
    st += [P("2. Environment set up on this PC", "h1"),
           P("Everything lives in <font face='Sans-B'>~/PlantDoctor</font>, inside an isolated Python virtual environment so nothing touches the system Python. "
             "No administrator (sudo) rights were needed."),
           table([
               ["Component", "Version / detail", "Why it was chosen"],
               ["Ubuntu", platform.freedesktop_os_release().get("PRETTY_NAME", "Linux"), "Your existing OS."],
               ["Python", platform.python_version(), "System Python with a project-local venv (.venv)."],
               ["PyTorch + torchvision", f"{torch.__version__} (CUDA 12.8 build)", "Industry-standard deep-learning library; ships pre-trained EfficientNet; uses your NVIDIA GPU."],
               ["GPU", f"{gpu}, 4 GB VRAM, driver 595", "Turing tensor cores allow fast mixed-precision (FP16) training."],
               ["FastAPI + Uvicorn", "Web API server", "Small, fast, typed Python web framework; automatic API docs at /api/docs."],
               ["HTML / CSS / JavaScript", "No framework", "The interface is three static files: fast, no build step, easy to modify."],
               ["Pillow, NumPy", "Image handling", "Decoding uploads and building the heatmap overlay."],
               ["Matplotlib, ReportLab", "Charts and this PDF", "Reproducible report generated from saved metrics."],
           ], [38 * mm, 50 * mm, W - 88 * mm]),
           Spacer(1, 8),
           P("How to use it", "h2")]
    st += B(["<b>Start the app:</b> <font face='Sans-B'>cd ~/PlantDoctor &amp;&amp; ./run.sh</font> then open http://127.0.0.1:8000",
             "<b>Re-train:</b> <font face='Sans-B'>.venv/bin/python train.py</font> (about 30–40 min on this GPU)",
             "<b>Field test:</b> <font face='Sans-B'>.venv/bin/python tools/eval_field.py</font>",
             "<b>Rebuild this report:</b> <font face='Sans-B'>.venv/bin/python tools/make_figures.py &amp;&amp; .venv/bin/python tools/make_report.py</font>",
             "<b>Rebuild the environment elsewhere:</b> <font face='Sans-B'>./setup.sh</font>"])

    # ---------------- 3. Data
    st += [PageBreak(), P("3. Data", "h1"),
           P("<b>PlantVillage</b> (Hughes &amp; Salathé, 2015; 'without augmentation' release on Mendeley Data) contains 54,305 photos of individual leaves of 14 crops, "
             "labelled as healthy or with one of 26 diseases, plus a 'background without leaves' class that this project keeps so the app can say "
             "\"no leaf found\" instead of guessing."),
           P(f"Images were split per class, with a fixed random seed, into <b>{n_train:,}</b> training (80%), <b>{n_val:,}</b> validation (10%) and "
             f"<b>{n_test:,}</b> test (10%) images. The test set was used exactly once, after training finished. The exact file lists are saved in "
             f"<font face='Sans-B'>reports/split.json</font> so the result can be reproduced."),
           P("<b>PlantDoc</b> (Singh et al., 2020) is a separate dataset of photos downloaded from the internet: real fields and gardens, several leaves per "
             f"image, hands, soil and sky in the background. Its {f['n_images']} test images in 27 overlapping classes were used <i>only</i> for evaluation, never for training."),
           fig("samples.png", "Figure 1. The domain gap in one picture. Training images (top) are uniform; real photos (bottom) are not."),
           fig("class_dist.png", "Figure 2. Training images per class. The dataset is imbalanced (e.g. orange greening vs. potato healthy); "
                                 "label smoothing and per-class metrics are used so rare classes are not ignored.", width=W * .92)]

    # ---------------- 4. Model & training
    ft = len(h) - 1
    st += [PageBreak(), P("4. How the model was trained", "h1"),
           P("Architecture: transfer learning", "h2"),
           P("Training a network from scratch needs millions of images. Instead the project starts from <b>EfficientNet-B0</b>, already trained on "
             "ImageNet's 1.2 million everyday photos, so it already knows edges, textures and colour patterns. Its final layer was replaced with a "
             f"new {len(sp['classes'])}-way classifier (with 30% dropout) and the network was fine-tuned on leaves. EfficientNet-B0 was picked because it gives "
             "ResNet-50-level accuracy with about a fifth of the parameters, fits comfortably in 4 GB of VRAM, and runs in tens of milliseconds per image."),
           P("Two-stage schedule", "h2")]
    st += B([f"<b>Stage 1 — head only (1 epoch):</b> backbone frozen, only the new classifier is trained (AdamW, LR 1e-3). This stops large random gradients "
             f"from the fresh layer damaging the pre-trained features.",
             f"<b>Stage 2 — full fine-tune ({ft} epochs):</b> all layers unfrozen, peak LR 3.3e-4 with a one-cycle cosine schedule (warm-up then decay), weight decay 1e-4. "
             f"The checkpoint with the best validation accuracy is kept.",
             "<b>Loss:</b> cross-entropy with label smoothing 0.1, which discourages over-confident outputs and makes the confidence score more meaningful.",
             "<b>Mixed precision (FP16)</b> on the GPU, batch size 48, 8 data-loading workers."])
    st += [P("Data augmentation (why it matters here)", "h2"),
           P("Every training image is randomly altered each time it is seen: random crop and zoom (60–100% of the area), horizontal and vertical flips, rotation up to 25°, "
             "brightness / contrast / saturation / hue jitter, occasional blur and random erasing of small patches. These imitate the variation of real photos "
             "and are the cheapest defence against the domain gap described in Section 6. They do not, however, add new backgrounds."),
           fig("curves.png", width=W * .8, caption="Figure 3. Training curves. Validation accuracy is higher than training accuracy because augmentation and dropout are only applied during training; "
                             "there is no sign of over-fitting."),
           table([["Epoch", "Stage", "Train loss", "Train acc.", "Val loss", "Val acc."]] +
                 [[x["epoch"], x["stage"], f"{x['train_loss']:.3f}", pct(x["train_acc"]), f"{x['val_loss']:.3f}", pct(x["val_acc"])] for x in h],
                 [16 * mm, 24 * mm] + [(W - 40 * mm) / 4] * 4),
           P("Loss values include the label-smoothing penalty, so they never reach zero even when every prediction is correct.", "cap")]

    # ---------------- 5. Results
    st += [PageBreak(), P("5. Results on PlantVillage (lab conditions)", "h1"),
           table([["Metric", "Value"],
                  ["Exact-class accuracy (top-1)", pct(t["test_acc"])], ["Correct class within top-5", pct(t["top5_acc"])],
                  ["Correct crop", pct(t["crop_acc"])], ["Macro-averaged F1 (all 39 classes equal weight)", f"{t['macro_f1']:.4f}"],
                  ["Test images", f"{t['n_test']:,}"]], [W * .6, W * .4]),
           Spacer(1, 8),
           P("The weakest classes are listed below. Most remaining errors are between diseases that look alike — for example corn gray leaf spot versus "
             "northern leaf blight (both elongated tan lesions), or tomato target spot versus early blight (both have concentric rings)."),
           table([["Class", "Precision", "Recall", "F1", "Test images"]] +
                 [[pretty(k), pct(v["precision"]), pct(v["recall"]), f"{v['f1']:.3f}", v["support"]] for k, v in worst],
                 [W * .44, W * .14, W * .14, W * .12, W * .16]),
           Spacer(1, 10),
           fig("confusion.png", "Figure 4. Confusion matrix on the test split. A perfect model would be a clean diagonal; each red number is a count of mistakes.")]

    # ---------------- 6. Field
    st += [PageBreak(), P("6. Does it work in the real world?", "h1"),
           P(f"To find out, the trained model — unchanged — was run on the PlantDoc test photos. Each PlantDoc folder was mapped to the matching PlantVillage class "
             f"(e.g. 'Tomato leaf late blight' maps to Tomato – Late blight)."),
           fig("lab_vs_field.png", "Figure 5. Identical model, very different outcomes. This gap is the single most important fact in this report."),
           table([["Field-photo metric", "Value"],
                  ["Exact-class accuracy (top-1)", pct(f["top1_acc"])], ["Correct class within top-5", pct(f["top5_acc"])],
                  ["Correct crop", pct(f["crop_acc"])],
                  ["Images the app flagged as 'verify' or 'not sure' (confidence &lt; 70%)", pct(f["share_flagged_low_conf"])],
                  ["Accuracy when the app was confident", pct(f["acc_when_confident"])],
                  ["Accuracy when the app flagged uncertainty", pct(f["acc_when_flagged"])]], [W * .7, W * .3]),
           Spacer(1, 8),
           P("Most frequent field mistakes", "h2"),
           table([["True class  ›  predicted as", "Count"]] + [[k, v] for k, v in f["top_confusions"][:8]], [W * .85, W * .15]),
           Spacer(1, 6)]
    st += [KeepTogether([P("Why it works on PlantVillage", "h2")] + B(["Disease symptoms on a single, centred leaf are distinctive: spot shape, colour, rings and mould textures are exactly what CNNs are good at.",
             "Transfer learning provides strong generic visual features, so ~44,000 images is plenty.",
             "Training and test images come from the same source, lighting and camera set-up, so the test is 'easy' in a statistical sense."]))]
    st += [P("Why it doesn't work as well in the field", "h2")]
    st += B(["<b>Domain shift.</b> Every training leaf sits on the same grey background under the same light. Field photos contain soil, sky, hands, many overlapping leaves, "
             "shadows and blur. The model has never seen those, and its features do not transfer cleanly.",
             "<b>Shortcut learning.</b> Researchers have shown PlantVillage classes can be partly predicted from the background pixels alone (Noyan, 2022). A model can quietly "
             "learn cues such as image brightness or leaf position rather than the disease itself, and those cues disappear outside the lab.",
             "<b>Whole scenes vs. single leaves.</b> PlantDoc images often show a whole plant. After resizing to 224 × 224 pixels, small lesions become a few pixels wide.",
             "<b>Look-alike symptoms and label noise.</b> Several diseases are hard to tell apart even for people from a photo; PlantDoc itself contains some ambiguous labels.",
             "<b>Closed set.</b> The model only knows 38 classes. Nutrient deficiency, sunscald, herbicide damage, insects or any unlisted disease will be forced into the nearest known class."])
    st += [fig("gradcam.png", "Figure 6. Grad-CAM heatmaps. On lab photos attention sits on lesions; on field photos it often spreads to background or neighbouring leaves — "
                              "a visual explanation of the accuracy drop.")]

    # ---------------- 7. Safeguards & improvements
    st += [PageBreak(), P("7. Safeguards built into the app", "h1")]
    st += B(["<b>Confidence gate.</b> 70% or higher: firm answer. 40–70%: 'possible match — verify' with a prompt to retake the photo. &lt; 40%: 'not sure', no diagnosis is asserted.",
             "<b>No-leaf class.</b> Photos with no leaf are recognised and rejected instead of being given a disease name.",
             "<b>Explainability.</b> The 'Where the model looked' heatmap lets the user check that the decision is based on the symptom and not on the background.",
             "<b>Top-5 alternatives</b> with probabilities, so near-ties are visible rather than hidden.",
             "<b>Plain-language disclaimer</b> and advice to confirm serious or notifiable diseases (late blight, citrus greening) with an agronomist."])
    st += [P("8. How to make it work better in the field", "h1"),
           table([["Improvement", "Expected effect", "Effort"],
                  ["Add real field photos to training (PlantDoc train split, iNaturalist, your own photos)", "Largest single gain; directly closes the domain gap", "Medium"],
                  ["Background replacement augmentation: paste segmented PlantVillage leaves onto random field backgrounds", "Breaks background shortcuts", "Medium"],
                  ["Leaf detection first (e.g. YOLO), then classify each leaf crop", "Handles whole-plant photos and multiple leaves", "High"],
                  ["Higher input resolution (e.g. 384 px) or a larger backbone (EfficientNet-B3, ConvNeXt-Tiny)", "Small lesions survive resizing", "Low"],
                  ["Temperature-scaling calibration and an 'unknown' detector", "Confidence becomes more trustworthy; fewer forced guesses", "Low"],
                  ["Collect user corrections from the app and retrain periodically", "Continual improvement on your local crops and conditions", "Medium"]],
                 [W * .5, W * .36, W * .14]),
           P("9. References", "h1")]
    st += B(["Hughes, D. P. &amp; Salathé, M. (2015). <i>An open access repository of images on plant health to enable the development of mobile disease diagnostics.</i> arXiv:1511.08060.",
             "Mohanty, S. P., Hughes, D. P. &amp; Salathé, M. (2016). <i>Using deep learning for image-based plant disease detection.</i> Frontiers in Plant Science 7:1419.",
             "Singh, D. et al. (2020). <i>PlantDoc: A dataset for visual plant disease detection.</i> CoDS-COMAD 2020.",
             "Tan, M. &amp; Le, Q. (2019). <i>EfficientNet: Rethinking model scaling for convolutional neural networks.</i> ICML 2019.",
             "Selvaraju, R. R. et al. (2017). <i>Grad-CAM: Visual explanations from deep networks via gradient-based localization.</i> ICCV 2017.",
             "Noyan, M. A. (2022). <i>Uncovering bias in the PlantVillage dataset.</i> arXiv:2206.04374.",
             "Dataset files: Mendeley Data doi:10.17632/tywbtsjrjv.1 (PlantVillage); github.com/pratikkayal/PlantDoc-Dataset (PlantDoc, CC BY 4.0)."])

    out = R / "PlantDoctor_Report.pdf"
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=22 * mm,
                      title="PlantDoctor — Technical Report", author="PlantDoctor").build(st, onFirstPage=deco, onLaterPages=deco)
    print(out)


if __name__ == "__main__":
    main()
