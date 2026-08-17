# BRAND_INTEGRATION_SNIPPET.md

Drop-in usage for `core/script_writer.py` and `core/seo_optimizer.py` to pull
tone/copy rules and lead-gen CTA text from the shared `marketing-ops` repo,
via `core/brand_aware_prompts.py` (which itself wraps `config/brand_loader.py`).

**UPDATE (2026-08-17):** `core/brand_aware_prompts.py` now exists in this repo
and does the heavy lifting -- script_writer.py and seo_optimizer.py only need
a single import + single function call each. This replaces the earlier
raw-snippet version of this doc.

## 1. In script_writer.py

```python
from core.brand_aware_prompts import get_script_style_block

# wherever the system/style prompt is currently assembled:
style_block = get_script_style_block()
# append `style_block` to the existing prompt/system message string
```

## 2. In seo_optimizer.py

```python
from core.brand_aware_prompts import get_seo_style_block, get_video_cta_text, get_pinned_comment_cta

style_block = get_seo_style_block()
# append `style_block` to the SEO/title/description generation prompt

cta_text = get_video_cta_text(long=False)
# append `cta_text` to the generated video description, after the
# LLM-generated content (do not let the LLM invent its own CTA)

pinned_comment_cta = get_pinned_comment_cta()
# use as-is or append to the LLM-generated pinned comment text
```

## 3. Do not duplicate brand or CTA strings locally

If script_writer.py or seo_optimizer.py have any local constants for tone or
a CTA/contact link, replace them with the `brand_aware_prompts` calls above
so there is exactly one source of truth.

## 4. Testing

```bash
python -m core.brand_aware_prompts
```

Prints the resolved script style block, SEO style block, video CTA text, and
pinned comment CTA -- confirms the marketing-ops fetch (and GITHUB_TOKEN, if
set) is working before wiring into the actual prompt logic.

## 5. Current blocker

`get_video_cta_text()` will return a placeholder string
(`[CONTACT INFO NOT YET CONFIGURED -- see marketing-ops/lead_capture.yaml]`)
until `lead_capture.yaml`'s `fallback_contact_method` field is filled in.
Do not ship video descriptions with that placeholder still in them -- check
for it in a post-generation validation step, or hold off applying the CTA
in seo_optimizer.py until the field is set.
