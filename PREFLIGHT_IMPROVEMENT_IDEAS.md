# Preflight Improvement Ideas for PDFDancer Proof Workflows

These notes capture product and technical ideas for using `pdfdancer-preflight`
as part of the new PDFDancer positioning:

> Automate production work on finished PDFs without going back to the source file.

The goal is not only to validate PDFs technically. The goal is to create a
credible proof system for publishers and marketing teams that need automated
PDF changes, variants, and batch production without breaking approved layouts.

## Strategic Role

Preflight should become part of the trust story:

1. FontSwap or another transformation tool shows a first-pass automated change.
2. Presscheck verifies technical production safety.
3. Before/after layout checks prove the automated change did not damage the PDF.
4. Representative-file evaluation turns edge cases into production rules before
   batch processing.

For publishers, this is especially important because the buyer objection is not
"can the tool edit a PDF?" The objection is:

> Can an automated PDF tool meet publisher production and typesetting quality
> expectations?

Preflight can help answer that, but only if it moves beyond raw technical JSON
and toward buyer-readable readiness and before/after fidelity evidence.

## Current Strengths

The existing tool is already useful:

- Target-based profiles for print and ebook checks.
- JSON reports with severity summaries.
- Before/after comparison mode.
- CI-friendly exit codes.
- Checks for renderability, page boxes, trim, bleed, embedded fonts, image DPI,
  color spaces, OutputIntent, transparency, annotations, forms, JavaScript,
  embedded files, blank pages, object bounds, and safe-area margins.
- A Java PDFBox analyzer with structured evidence extraction.

This makes it credible as a technical production-safety layer.

## Current Gap

The tool does not yet prove visual or typesetting fidelity.

It can say:

- The PDF is processable.
- Fonts are embedded or missing.
- Images meet a DPI target.
- Boxes, color, annotations, and interactive content meet policy.
- The after PDF did not add or worsen configured preflight findings.

It does not yet say:

- Line breaks stayed stable.
- Page breaks stayed stable.
- Text/image positions did not drift beyond tolerance.
- Tables, footnotes, headings, and dense pages survived the change.
- A font migration preserved the book's layout well enough for production.
- Visual differences are limited to expected edit regions.

That distinction matters. Presscheck should not be positioned as complete proof
until layout fidelity checks exist.

## Productized Surface

Avoid exposing the public-facing concept as only "preflight" across all markets.

Recommended umbrella:

> PDF Production Readiness Check

Publisher-specific label:

> Publisher PDF Automation Readiness Check

Marketing-specific label:

> Template Readiness Check

The underlying tool can remain Presscheck. The website and reports should speak
in terms of readiness, production risk, and recommended next steps.

## Proof Ladder

A strong publisher workflow could be:

1. Public instant test
   - User uploads a PDF to FontSwap or a similar tool.
   - They see a first-pass automated transformation.

2. Technical preflight
   - Presscheck inspects the input and output PDFs.
   - It flags production risks such as missing fonts, bad boxes, low image DPI,
     OutputIntent problems, unsafe annotations, JavaScript, transparency, and
     safe-area issues.

3. Before/after comparison
   - The tool checks whether the transformed PDF introduces new production
     risks compared with the original.

4. Layout fidelity report
   - New checks compare page count, boxes, text bounds, object bounds, font
     resources, rendered pages, and visual differences.

5. Representative-file evaluation
   - If first-pass output needs tuning, the customer sends hard files from the
     real backlist or collateral workflow.
   - PDFDancer calibrates mappings, rules, tolerances, and exceptions.

6. Batch run
   - Only after representative files pass the agreed checks.

## Buyer-Readable Readiness Report

Add a report layer above raw JSON.

Possible readiness levels:

- `ready`
- `ready_with_review`
- `needs_calibration`
- `not_recommended`

Example summary:

```text
Automation readiness: Needs calibration

Main risks:
- 2 non-embedded fonts
- 14 pages with text near trim
- no OutputIntent

What this means:
The file is technically processable, but production migration should be tested
on representative pages before batch processing.

Recommended next step:
Run a calibrated font-migration evaluation on 5-10 representative PDFs.
```

Suggested sections:

- Overall readiness.
- Technical production safety.
- Layout fidelity risk.
- Font and text risk.
- Image and color risk.
- Print/ebook readiness.
- Before/after regression status.
- Recommended next step.
- Checks passed.
- Checks needing review.
- Raw findings link or attachment.

## Dedicated Target Profiles

Add profiles that match actual product workflows instead of only generic print
and ebook targets.

Suggested profiles:

- `publisher-font-migration.yml`
- `publisher-print-book.yml`
- `publisher-ebook.yml`
- `publisher-backlist-update.yml`
- `marketing-collateral-template.yml`
- `marketing-print-collateral.yml`
- `marketing-digital-collateral.yml`

Profile ideas:

### Publisher Font Migration

Focus:

- Embedded fonts before and after.
- Font resources changed only according to the intended mapping.
- Page count unchanged.
- Page boxes unchanged.
- Text bounds drift within tolerance.
- No new safe-area violations.
- No new low-resolution images.
- No new color/OutputIntent/interactive regressions.
- Optional rendered visual diff.

### Publisher Print Book

Focus:

- TrimBox, BleedBox, MediaBox, CropBox policy.
- Page count and parity policy.
- OutputIntent required.
- Image DPI.
- RGB image policy.
- Registration color misuse.
- Spot color policy.
- Safe-area margins.
- Blank pages allowed only by policy.
- Interactive content, forms, JavaScript, and embedded files disallowed.

### Publisher Ebook

Focus:

- MediaBox required.
- Links allowed but checked.
- JavaScript and embedded files disallowed.
- Forms controlled by policy.
- Image DPI threshold lower than print.
- PDF/A/PDF/X metadata informational unless required.
- Future: bookmarks, TOC links, document language, tags, alt text.

### Marketing Collateral Template

Focus:

- Fonts embedded.
- Placeholder text detectable if placeholders are part of the workflow.
- Logo/image slots detectable and stable.
- Page boxes stable.
- No unsafe interactive content.
- Images have enough resolution for intended output.
- Before/after text and image bounds do not drift outside expected edit regions.

## Before/After Layout Fidelity Checks

The existing comparison checks whether findings changed. Add comparison checks
for structural and visual layout stability.

Suggested checks:

- Page count unchanged unless explicitly expected.
- Page boxes unchanged within tolerance.
- Page rotation unchanged.
- Trim, bleed, crop, and media geometry unchanged.
- Font resources changed only according to an allowed mapping.
- New non-embedded fonts are never introduced.
- Text glyph count is unchanged or changes only within expected edit regions.
- Text bounds are unchanged within tolerance outside expected edit regions.
- Image/Form XObject bounds are unchanged within tolerance outside expected
  edit regions.
- No new content near trim or outside safe area.
- No new blank pages.
- No new annotations, forms, JavaScript, or embedded files.
- No new low-resolution image placements.
- No new color-space, overprint, transparency, or OutputIntent regressions.

## Rendered Visual Diff

Add an optional rendered comparison mode.

Possible approach:

- Render before and after pages with Ghostscript or another deterministic
  renderer.
- Compare raster output page by page.
- Support ignore regions for intended edits.
- Report per-page difference percentage and bounding boxes.
- Fail when differences appear outside expected regions or exceed tolerance.

Important caveat:

Rendered visual diff is powerful but can be noisy. It should be configurable and
should not replace structural checks. It is best used as a high-signal proof
artifact for publisher evaluations.

## Line and Text Stability Checks

For publisher-quality proof, add checks that approximate line stability.

Possible evidence to collect:

- Text clusters by page and y-position.
- Line bounding boxes.
- Line widths.
- Font name, size, and subtype per line cluster.
- Approximate text content where extractable.
- Glyph counts per line cluster.

Comparison checks:

- Same number of line clusters outside expected edit regions.
- Y positions within tolerance.
- Line widths within tolerance.
- No unexpected line moved to next page.
- No unexpected page-ending drift.

This will be imperfect on complex PDFs, but even a conservative heuristic would
be more persuasive than generic "layout preserved" claims.

## Font Migration Specific Checks

Font migration is a strong proof case, but it needs special reporting.

Suggested checks:

- Original fonts detected.
- Replacement fonts detected.
- Only expected font families changed.
- No fallback or system fonts introduced.
- No new non-embedded fonts introduced.
- Text size and horizontal scale changes within tolerance.
- Text bounds drift within tolerance.
- Page count unchanged.
- Page-ending and line-cluster checks pass.
- Visual diff outside text regions is near zero.

Recommended wording:

> FontSwap reveals whether your PDFs are good candidates for automated font
> migration. When the first pass needs tuning, representative files are used to
> build a production-safe rule set.

Avoid implying:

> Upload any book, swap font, done.

## Marketing Collateral Specific Checks

Marketing collateral proof is less about traditional typesetting and more about
brand-controlled variant generation.

Suggested checks:

- Template placeholders are present and detectable.
- Replacement text inherits intended font, size, and color.
- Logos/images fit within intended slots.
- No new overlap with adjacent content.
- Output page boxes remain stable.
- Print assets meet target DPI.
- The output has no unsafe interactive content.
- Batch-generated variants pass the same target profile.

Possible report language:

```text
Template readiness: Ready with review

The PDF is suitable for automated partner variants. Logo slot and contact
fields were detected. One page has content close to trim and should be checked
before print production.
```

## API and Report Format Ideas

Keep raw JSON for machines, but add a stable higher-level report model.

Suggested top-level fields:

```json
{
  "workflow": "publisher_font_migration",
  "readiness": "needs_calibration",
  "summary": {},
  "risk_groups": [],
  "recommendations": [],
  "checks": [],
  "raw_findings": []
}
```

Suggested risk group shape:

```json
{
  "id": "layout_fidelity",
  "label": "Layout fidelity",
  "status": "needs_review",
  "message": "Text bounds changed on 3 pages outside expected regions.",
  "evidence": []
}
```

Suggested recommendation shape:

```json
{
  "priority": "high",
  "message": "Run calibrated evaluation on representative chapter PDFs.",
  "reason": "Font replacement changed text bounds beyond tolerance on dense pages."
}
```

## Website Integration

The website should not ask publishers to trust a generic demo.

Recommended story:

> We do not ask publishers to trust a generic demo. We test representative PDFs,
> inspect production risks, compare before/after output, and only scale the
> workflow after the rules pass.

Suggested CTAs:

- Check PDF automation readiness.
- Test representative PDFs.
- Run a font-migration readiness check.
- Evaluate a backlist workflow.

Suggested proof artifacts:

- Downloadable before/after PDFs.
- A sample readiness report.
- A visual diff screenshot or report.
- A case-style report showing first-pass result, issues found, adjustments made,
  and final production-safe output.

## Implementation Roadmap

Near-term:

1. Add buyer-readable readiness summary generation.
2. Add dedicated target profiles for publisher and marketing workflows.
3. Add report grouping by risk area.
4. Add recommendation generation from known findings.
5. Add sample reports for website use.

Medium-term:

1. Add before/after structural fidelity checks.
2. Add font-migration-specific comparison checks.
3. Add expected edit regions so legitimate changes do not cause false failures.
4. Add line-cluster evidence and comparison.
5. Add visual diff mode.

Longer-term:

1. Add cover-specific book checks.
2. Add bleed-content quality analysis.
3. Add deeper color checks such as TAC, rich black, and black text policies.
4. Add OutputIntent profile details.
5. Add ebook navigation and accessibility checks.

## Positioning Caveat

Preflight should make the proof more credible, not overstate certainty.

Good claim:

> We inspect the PDF, identify automation risks, and prove the transformation
> on representative files before batch processing.

Risky claim:

> Our preflight guarantees publisher-quality automation.

The better message is that publishing PDFs are not uniform. The question is not
whether every title works untouched. The question is whether the required
corrections can be captured as rules and applied reliably across the backlist.
