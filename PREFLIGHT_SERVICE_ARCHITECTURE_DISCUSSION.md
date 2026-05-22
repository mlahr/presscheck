# Preflight Service Architecture Discussion

## Current Intent

This preflight system is planned as a separate internal service, not part of the backend.

Likely early use:

- Internal tool
- CI-oriented
- CLI-first
- One PDF in, inspect that PDF
- Exactly one input PDF per run
- Report/evidence only
- No auto-fix
- No PDF rewriting
- No retained intermediate artifacts

Possible later direction:

- Released as open source under AGPL or a compatible license
- AGPL tooling is acceptable

Primary target:

- Print safety

The architecture should allow custom targets from the beginning.

HTTP/service mode may come later. The core should not depend on CLI-specific assumptions, but the first interface is CLI.

The CLI exit code is based on configured severity. CI should be able to fail when findings meet or exceed the target's fail severity.

The fail threshold is target-configurable. For example, one target may fail at error, while another may fail at warning.

Output is JSON. No separate human-readable report format is planned initially.

JSON output goes to stdout.

The JSON format may change freely during early development. A stable output contract is not required yet.

Raw tool logs and log excerpts are not included in JSON output.

Severity levels are:

- info
- warning
- error

## Meaning of Evidence-Only

The service should collect evidence. It should not pretend to prove that a PDF is correct.

Evidence can be factual or heuristic.

High-confidence evidence examples:

- Font is not embedded.
- Page has no TrimBox.
- Image effective resolution is below a threshold.
- Object uses DeviceRGB.
- Transparency ExtGState exists.
- OutputIntent is missing.

Heuristic evidence examples:

- JPEG artifacts may be visible.
- Rich black may be unsafe.
- Drop shadow may flatten poorly.
- Text may be too small for the intended print process.
- Bleed appears insufficient because painted content does not extend past trim.

Unstable heuristics are acceptable if they are clearly represented as heuristic evidence and remain traceable.

## Visual Rendering Agreement

Visual rendering agreement is not planned.

This means the service should not compare raster output between multiple renderers such as Ghostscript and MuPDF.

Excluded model:

```text
input.pdf
  -> render with Ghostscript
  -> render with MuPDF
  -> compare rasters
  -> report renderer disagreement
```

That class of check is out of scope.

Render-derived checks may still be relevant if they produce direct print-safety evidence from one engine, for example:

- Ghostscript can process the PDF.
- Ghostscript emits warnings.
- Ink coverage / TAC can be estimated.
- Raster-derived bleed checks.
- Raster-derived art-outside-trim checks.
- Transparency or flattening warnings from a print-oriented engine.

These are not visual agreement checks because they do not compare two renderers.

Ghostscript is a core dependency for print-safety preflight. Ghostscript-based checks should always run.

There is no separate fast/deep mode.

MuPDF has no planned role.

veraPDF has no planned role.

PDFBox is the main structural inspection library.

Expected PDFBox role:

- Fonts
- Images
- Page boxes
- Resources
- Color spaces
- OutputIntent
- Transparency declarations

LCMS2 is the planned color-management component.

Expected LCMS2 role:

- ICC profile validation
- Color transform checks
- Color-management evidence

LCMS2 is not a general PDF inspection tool.

## What "Targets" Means

A target is the intended output condition or rule set.

The same PDF can be acceptable for one target and unsafe for another.

Targets are config-file based only. There are no built-in target profiles in the initial architecture.

Every run requires an explicit target config.

Example targets:

```text
digital-preview
print-cmyk
newspaper
premium-offset
pdf-x-1a-like
custom-house-style
```

Examples:

```text
Evidence:
  image on page 2 has effective resolution 142 DPI

Interpretation:
  digital-preview: probably acceptable
  newspaper: maybe warning
  premium-offset: likely error
```

Custom targets matter because print safety depends on intended production conditions.

Target parameters might include:

- Expected trim size
- Required bleed
- Minimum image DPI
- Maximum TAC / ink coverage
- Allowed color spaces
- Whether RGB is allowed
- Whether spot colors are allowed
- Whether live transparency is allowed
- Minimum text size
- Whether PDF/X-like constraints are expected

Even if the service is evidence-only, targets may still be needed to decide what measurements and thresholds to apply.

Target config controls check selection. Checks should be individually enableable and disableable.

Geometry checks can compare PDF page boxes against the expected trim size from the target config.

Target config should support page-size tolerance for geometry checks.

Bleed checks should include both structural checks and raster-derived checks:

- Structural: inspect page boxes and required bleed dimensions.
- Raster-derived: check whether artwork appears to extend into the bleed area.

Art-outside-boundary checks should be configurable per check. The relevant boundary may be TrimBox, BleedBox, or a target-defined safe area.

Target config controls severity per check. Severities are not fixed by the tool.

Thresholds are configurable per check. Shared defaults can be considered later if target files become repetitive.

Suppressions and waivers are not planned.

For target/check/config design questions, prefer target-configurable behavior. Different print workflows may require different choices, so requirements such as crop marks, geometry boundaries, allowed features, thresholds, and severities should live in target config unless there is a strong reason to hardcode them.

## Process Shape Options

### Core Language

The coordinator/core should be written in Python.

Reasons:

- The architecture is still evolving.
- Python is strong for orchestration, JSON, config, subprocesses, and rapid iteration.
- Native dependencies can be handled locally on macOS and inside Linux containers.
- PDFBox does not require the core to be JVM-based; it can be invoked through a Java analyzer CLI/JAR.
- Ghostscript can be invoked as an external tool.
- LCMS2 can be integrated later through Python bindings, `ctypes` / `cffi`, or a native helper.

The core language decision does not require all analyzers to be written in Python.

Expected shape:

```text
Python preflight CLI
  -> invokes Ghostscript
  -> invokes PDFBox analyzer CLI/JAR
  -> invokes LCMS2/color helper if needed
  -> merges analyzer evidence
  -> applies target config/severity
  -> emits JSON
```

### Option A: Single Service Process With Analyzer Modules

Shape:

```text
preflight-service
  -> font analyzer
  -> image analyzer
  -> color analyzer
  -> geometry analyzer
  -> print-process analyzer
  -> heuristic quality analyzer
```

This may shell out to external tools where useful.

Pros:

- Simpler to build.
- Easier to run in CI.
- Easier to reproduce locally.
- Fewer operational moving parts.
- Fits the one-PDF-in model.
- Allows clear analyzer boundaries without distributed infrastructure.

Cons:

- One process/image must contain all tool dependencies.
- Tool crashes and timeouts need careful handling.
- Less isolation between analyzers.
- Harder to scale individual analyzer types independently.

Current leaning:

- Favor this early.
- Keep analyzer boundaries clear in code.
- Avoid distributed workers until there is a concrete need.

### Option B: Coordinator With Isolated Analyzer Workers

Shape:

```text
coordinator
  -> font worker
  -> image worker
  -> color worker
  -> geometry worker
  -> print-process worker
```

Pros:

- Stronger isolation.
- Easier to sandbox risky tools.
- Workers can use different languages and dependencies.
- Better fit if service later runs under load.
- Better fit if expensive analyzers need independent scaling.

Cons:

- More architecture before the problem is clear.
- More difficult CI setup.
- More operational failure modes.
- Forces protocol design too early.
- Easy to overbuild.

Current leaning:

- Do not start here.
- Reconsider only if tool isolation, scaling, or dependency conflicts become real problems.

## Intermediate Artifacts

Intermediate artifacts should not be retained.

Expected model:

```text
input PDF
  -> temporary workspace
  -> analyzers run
  -> collect evidence
  -> delete temporary files
  -> return evidence
```

Examples of artifacts not retained:

- Rendered page PNGs
- Object dumps
- Intermediate converted PDFs
- Long-lived tool logs

However, findings should retain enough provenance to be debugged without saved artifacts.

Examples:

```text
source tool: Ghostscript
page: 3
check: total ink coverage
observed value: 342%
threshold: 300%
```

## Traceability Requirement

Every finding should be traceable.

Where possible, a finding should identify:

- Page
- Object or resource
- Analyzer
- Source tool
- Observed value
- Threshold or rule, if applicable
- Whether the evidence is factual or heuristic

Weak example:

```text
PDF has image problems.
```

Better example:

```text
page 5
image XObject Im12
effective DPI 118 x 121
threshold 300
source: image analyzer
evidence type: measured
```

Traceability is an architectural requirement, not merely a report-format detail.

Findings should include tool/analyzer identity and measured values where relevant. They should not include raw logs or log excerpts.

## Failure Modes To Consider

### Fonts

- Missing fonts
- Non-embedded fonts
- Corrupted fonts
- Faux bold / italic
- Type too small
- Overprint text issues

### Images

- Low image resolution
- RGB images in CMYK workflows
- Incorrect compression
- Missing image links
- Transparency problems
- JPEG artifacts
- Image scaling beyond thresholds

### Color

- RGB objects in CMYK jobs
- Spot colors incorrectly named
- Mixed color spaces
- Rich black problems
- Ink coverage / TAC too high
- ICC profile mismatches
- Registration color misuse

### Page Geometry

- Wrong trim size
- Missing bleed
- Insufficient bleed
- Incorrect crop marks
- Art outside trim area
- Incorrect page boxes: MediaBox, TrimBox, BleedBox

### Transparency And Effects

- Live transparency not allowed
- Blend mode issues
- Flattening risks
- Drop shadow rendering issues

## Analyzer Categories

Use domain-oriented analyzer categories that match print-preflight language:

- Document integrity
- Fonts
- Images
- Color
- Geometry
- Transparency and effects

### Document Integrity

Owns file-level processability:

- Malformed PDF
- Encrypted or locked PDF
- Unsupported PDF version
- XRef / object stream issues
- Parser warnings
- Tool processing failures

Analyzer failures are fail-closed. If an analyzer cannot complete, that failure is itself preflight evidence.

Encrypted or password-protected PDFs are unsupported and should be treated as document-integrity failures.

### Fonts

Owns text and font production risks:

- Missing fonts
- Non-embedded fonts
- Corrupted fonts
- Faux bold / italic
- Type too small
- Font encoding or glyph risks

### Images

Owns placed-image quality risks:

- Low effective resolution
- Excessive scaling
- Compression issues
- JPEG artifact risk
- Image masks or soft masks when image-specific

### Color

Owns color and print-process color risks:

- RGB objects in CMYK workflows
- Mixed color spaces
- Spot color names
- Rich black
- Ink coverage / TAC
- ICC profile mismatch
- Registration color misuse
- OutputIntent
- Overprint policy issues

### Geometry

Owns page-production geometry:

- Trim size
- MediaBox / TrimBox / BleedBox / CropBox
- Missing bleed
- Insufficient bleed
- Crop marks
- Art outside trim
- Objects too close to trim

### Transparency And Effects

Owns transparency and effect risks:

- Live transparency
- Alpha
- Soft masks
- Blend modes
- Transparency groups
- Flattening risk
- Drop shadows

### Overlap Rule

When a finding could fit multiple categories, place it where a user would naturally investigate first.

Examples:

- RGB image in a CMYK workflow belongs to color, with evidence pointing to the image object.
- Low image DPI belongs to images.
- Soft mask attached to an image belongs to transparency and effects, with evidence pointing to the image object.
- Missing TrimBox belongs to geometry.
- Drop shadow belongs to transparency and effects.

## Current Architectural Direction

Current working direction:

```text
Separate internal preflight service
  AGPL-compatible tooling acceptable
  CI-oriented
  one PDF per run
  print-safety focused
  custom target parameters from the beginning
  no visual renderer agreement
  no retained intermediate artifacts
  unstable heuristics allowed if labeled
  every finding traceable to evidence
```

The next architecture discussion should focus on analyzer categories and boundaries, not report schema or implementation.
