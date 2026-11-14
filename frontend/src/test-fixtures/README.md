# Test fixtures

`ndvi-yangon-2015-2024-annual-2026-11-13.json` is the genuine saved output of the live NDVI retrieval
captured on 2026-11-13, before NDVI trends switched to the Seasonal Kendall method. It is kept only so
tests can exercise an annual record with no eligible years and no trend. The app never loads it; the
offline demo uses `frontend/public/snapshots/`.
