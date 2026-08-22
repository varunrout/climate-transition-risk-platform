"""M6 phase 2: energy-feature evaluation and score-integration gating.

Everything in this package is research/evaluation code, not production
pipeline code -- it reads the silver/gold artifacts M0-M6-phase-1 already
produce, computes evidence, and writes to gold/research/m6/. Nothing here
is imported by ingest/build-silver/backtest/score/publish; the dependency
runs one way, from research into the existing pipeline's public outputs.
"""
