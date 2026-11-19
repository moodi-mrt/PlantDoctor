# PlantDoctor — crop & plant disease detection

Upload a leaf photo in the browser → crop, disease, confidence, next steps, and a Grad-CAM heatmap.

## Run
    ./run.sh                      # http://127.0.0.1:8000

## Layout
    app/server.py        FastAPI server (/api/predict, /api/info, /api/docs)
    app/inference.py     model loading, prediction, Grad-CAM, confidence gate
    app/knowledge.py     cause / symptoms / actions per class
    app/static/          browser interface (HTML/CSS/JS, no build step)
    train.py             fine-tunes EfficientNet-B0 on PlantVillage
    tools/eval_field.py  tests the model on real field photos (PlantDoc)
    tools/make_figures.py, tools/make_report.py   build reports/PlantDoctor_Report.pdf
    models/              trained weights
    reports/             metrics, figures, training log, PDF report
    data/                PlantVillage (train) + PlantDoc test (field eval)

## Results
- PlantVillage test set: 99.8% accuracy (lab-style photos)
- PlantDoc field photos: 31.7% exact / 62.9% top-5. See the PDF, section 6, for why.

## Rebuild from scratch
    ./setup.sh && .venv/bin/python train.py && .venv/bin/python tools/eval_field.py
