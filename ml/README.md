# Image model: deliberately not in the product yet

Section 5.1 of the concept proposal says the long-term plan is an AI model
trained on **properly labelled** banana and matooke disease images, and that the
*initial prototype* should use a guided symptom questionnaire plus a curated
knowledge base. That is exactly how this repository is built:

- the shipped answer path is `app/engine/diseases.py` (questionnaire + knowledge
  base + confidence floor + referral);
- this folder holds the training scaffold for the later stage, and it is **never
  imported by `app`**, so the web app has no torch dependency and no one can
  mistake its output for a diagnosis.

## Why the model is not here yet

Three things have to happen first, and none of them is coding:

1. **Data.** Public banana-leaf image sets are mostly research photographs from
   a few regions, taken at particular growth stages, often of *Musa* dessert
   bananas rather than East African cooking matooke. A model trained on those
   will look accurate and fail in a Luwero garden.
2. **Labels.** Every image used for evaluation needs an agronomist's verdict,
   ideally with a laboratory result for bacterial cases. Symptom-only labels
   cannot separate BXW from Moko, which is precisely the confusion that harms
   farmers.
3. **Referral route.** A model is only responsible if a low-confidence answer
   goes to a person. The referral machinery (`referred`, `referral_reason`,
   expert outcome on `disease_case`) exists in the app already; the image model
   has to plug into it, not around it.

## Data collection protocol we propose

| Step | Detail |
| --- | --- |
| Sites | 3 districts in the matooke belt, 8 gardens each, dry and wet season visits |
| Per plant | 4 photos: whole plant, youngest fully open leaf (both sides), male bud, cut petiole showing the inside |
| Metadata | date, district, variety, age of mat, previous sprays, whether a neighbour mat is symptomatic, phone GPS |
| Ground truth | district agricultural officer records a field diagnosis; suspicious bacterial cases get a lab sample |
| Volume target | >= 300 images per class for the six most common conditions before any accuracy is quoted |
| Consent | written informed consent per farmer, images stored with the profile, withdrawal honoured by deleting rows (Data Protection and Privacy Act 2019) |
| Split | held-out gardens, not held-out images: images from the same garden leak |

## Running the scaffold

```bash
pip install torch torchvision
mkdir -p ml/data/bxw ml/data/black_sigatoka ml/data/healthy
# drop images into the class folders, then:
python ml/train_matooke_vision.py --data ml/data --epochs 12
```

It will **refuse** to train a "usable" model when any class has fewer than 60
images (override only with `--force`, for a pipeline smoke test), it reports
per-class precision and recall rather than a single accuracy, and it exits
non-zero if validation accuracy is below 0.75 or any class recall is below 0.6.
The output `model_card.json` records those limitations next to the weights.

## Acceptance criteria before wiring it into the app

- [ ] Expert-reviewed test set from gardens not seen in training
- [ ] Probability calibration measured (e.g. expected calibration error)
- [ ] Confidence floor with automatic referral, tested against the questionnaire ranking
- [ ] Behaviour on blurry, backlit and partially occluded field photos characterised
- [ ] Sign-off from an agricultural officer on how results are worded
- [ ] A "wrong answer" path: how a farmer reports it and how that feedback is used
