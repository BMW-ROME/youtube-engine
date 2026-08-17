# BRAND_INTEGRATION_SNIPPET.md

Drop-in usage for `core/script_writer.py` and `core/seo_optimizer.py` to pull
tone/copy rules from the shared `marketing-ops` brand file via
`config/brand_loader.py`, instead of hardcoding tone locally.

This file does NOT modify script_writer.py or seo_optimizer.py directly --
their current internals were not readable via this session, so integration
is provided as a copy-in snippet for whoever (agent or you) next edits those
files, to avoid overwriting in-progress work blind.

## 1. Import (top of file, alongside existing imports)

```python
from config.brand_loader import (
    get_brand_identity,
    get_voice_tone_descriptors,
    get_language_rules,
    get_primary_niches,
)
```

## 2. In script_writer.py -- wherever the LLM prompt for script generation is built

Before constructing the prompt string / messages payload, pull brand context:

```python
brand = get_brand_identity()
tone_descriptors = get_voice_tone_descriptors()          # e.g. ["versatile", "deep", "warm", "hypnotic"]
register = brand.get("voice_tone", {}).get("register", "")
delivery_notes = brand.get("voice_tone", {}).get("delivery_notes", "")
lang_rules = get_language_rules()                          # {"do": [...], "dont": [...]}
niches = get_primary_niches()
```

Then fold these into the system/style prompt, e.g.:

```python
brand_style_block = (
    f"Voice/tone: {', '.join(tone_descriptors)}. Register: {register}. "
    f"{delivery_notes}\n"
    f"Do: {'; '.join(lang_rules['do'])}\n"
    f"Don't: {'; '.join(lang_rules['dont'])}\n"
    f"Relevant niches/topics to favor when applicable: {', '.join(niches)}"
)
```

Append `brand_style_block` into the existing prompt/system message construction
(exact insertion point depends on script_writer.py's current prompt-building
function -- look for where the system prompt or style instructions are
currently assembled, and append there rather than replacing it).

## 3. In seo_optimizer.py -- wherever titles/descriptions/tags are generated

Same pattern: call `get_brand_identity()` once per invocation (or cache at
module load, respecting brand_loader's own caching), and thread
`tone_descriptors` + `lang_rules["dont"]` into the prompt or post-processing
step that filters/validates generated titles and descriptions, so SEO copy
doesn't drift into generic AI-marketing phrasing that language_rules.dont
flags.

## 4. Do not duplicate brand strings locally

If script_writer.py or seo_optimizer.py currently have any local constants
like `TONE = "warm and engaging"` or similar, replace them with calls into
`brand_loader` rather than keeping both -- otherwise the two sources can
drift out of sync.

## 5. Testing

`config/brand_loader.py` is safe to run standalone:

```bash
python -m config.brand_loader
```

This prints which source the brand identity was loaded from (remote / local
cache / built-in default) plus the resolved tone descriptors and niches --
useful for confirming GITHUB_TOKEN is working before wiring into the prompt
logic above.
