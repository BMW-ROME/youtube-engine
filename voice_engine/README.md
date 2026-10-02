# Recovered voice engine

This package resumes the original September 5 Chapter 2.1-2.4 contracts. Original
archive files remain unchanged. Evidence and distillation implementations were
recovered rather than redesigned; the missing panel Python module was repaired
against its existing definition and test contract.

The eight WMW identities and their skepticism/humor rules are preserved.
The panel module validates independently supplied reactions. It does not generate
reactions, transcribe recordings, or infer vocal delivery from text.

The master_asset_template.json is an example contract shape, not JSON Schema.
Distillation ranks supplied ideas/evidence, retains tiers and conflicts, rejects
orphaned references, and respects minimum confidence. Outputs are production and
business hypotheses, never proof of market demand. Numeric ranks are heuristics,
not calibrated probabilities or market validation.

Run `python -m pytest -q tests/test_voice_engine.py` from the repository root.
Its chain fixture is synthetic. A real recording/transcript exercise and independent
panel evaluation remain required for the project's first real end-to-end test.

No private recording or user transcript is included in this package. Analysis
must preserve the original source, use the same asset ID, and only cite modalities
that were actually supplied. The YouTube adapter is not yet connected to these
voice-engine components.
