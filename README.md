# PDFdancer Preflight

Architecture prototype for an internal, CI-oriented PDF preflight tool.

The prototype currently proves the basic flow:

```text
target config -> analyzers -> findings -> severity evaluation -> JSON file -> exit code
```

## Requirements

- Python 3.13+
- uv
- Ghostscript available as `gs`
- Java 17+

## Run

Use the sample target config:

```bash
uv run pdfdancer-preflight --target examples/targets/print-basic.yml --output result.json input.pdf
```

The CLI writes JSON to the output file and exits nonzero when findings meet or exceed the target's `fail_at` severity.

Example with a known PDF:

```bash
uv run pdfdancer-preflight \
  --target examples/targets/print-basic.yml \
  --output result.json \
  /path/to/file.pdf
```

Logs are written to stderr. The default log level is `info`.

```bash
uv run pdfdancer-preflight \
  --target examples/targets/print-basic.yml \
  --output result.json \
  --log-level debug \
  /path/to/file.pdf
```

## PDFBox Analyzer

The Python CLI calls PDFBox through an external Java analyzer jar.

Build it before running targets that enable PDFBox-backed checks:

```bash
./gradlew :analyzers:pdfbox:fatJar
```

Default jar path:

```text
analyzers/pdfbox/build/libs/pdfbox-analyzer.jar
```

Override the jar path:

```bash
PDFDANCER_PREFLIGHT_PDFBOX_ANALYZER_JAR=/path/to/pdfbox-analyzer.jar \
  uv run pdfdancer-preflight --target examples/targets/print-basic.yml --output result.json input.pdf
```

Run the analyzer directly:

```bash
java -jar analyzers/pdfbox/build/libs/pdfbox-analyzer.jar input.pdf
```

## Tests

Run the test suite:

```bash
uv run pytest
```

Run the Python linter:

```bash
uv run ruff check
```

Run the Java analyzer tests:

```bash
./gradlew :analyzers:pdfbox:test
```

## Inspect Reports

Reports include a built-in summary:

```json
{
  "summary": {
    "total_findings": 3,
    "by_severity": {
      "info": 0,
      "warning": 1,
      "error": 2
    },
    "by_check": [
      {
        "check_id": "images.low_effective_resolution",
        "category": "images",
        "severity": "error",
        "count": 1,
        "pages": [1, 2]
      }
    ],
    "color": {
      "image_color_space_findings_by_family": {
        "ICCBasedRGB": 77,
        "Indexed": 17
      }
    }
  }
}
```

Print the summary:

```bash
jq '.summary' report.json
```

Compact summary table:

```bash
jq -r '
  .summary.by_check[]
  | [.severity, .category, .check_id, .count, (.pages | join(","))]
  | @tsv
' report.json
```

Inspect raw findings if needed:

```bash
jq '.findings[]' report.json
```

## Current Checks

- `document_integrity.ghostscript_processable`
- `fonts.non_embedded`: grouped by font name and subtype
- `images.low_effective_resolution`: page and Form XObject image placements
- `color.image_color_space_policy`: target-driven policy for image placement color spaces
- `color.output_intent_required`: target-driven document-level OutputIntent requirement
- `transparency.live_transparency_policy`: target-driven policy for applied live transparency features
- `geometry.page_boxes_present`
- `geometry.trim_size_matches`
- `geometry.bleed_margin_at_least`
- `geometry.object_bounds_within_box`: placed image/Form XObject bounds within a configured page box

## Target Config

Every run requires a target YAML file. The current format is intentionally small and may change.

Example targets:

- `examples/targets/print-basic.yml`: print-oriented; requires trim and bleed boxes.
- `examples/targets/ebook.yml`: digital/ebook-oriented; only requires `MediaBox`, disables trim-size checks, and uses lower image DPI severity/thresholds.

Example:

```yaml
fail_at: error
checks:
  document_integrity.ghostscript_processable:
    enabled: true
    severity: error
    timeout_seconds: 60
  fonts.non_embedded:
    enabled: true
    severity: error
    timeout_seconds: 60
  images.low_effective_resolution:
    enabled: true
    severity: error
    min_dpi: 300
    timeout_seconds: 60
  color.image_color_space_policy:
    enabled: true
    severity: warning
    severity_by_family:
      DeviceRGB: error
      ICCBasedRGB: warning
      DeviceCMYK:
      ICCBasedCMYK:
      DeviceGray:
      ICCBasedGray:
      Indexed: warning
      Separation: warning
      DeviceN: warning
      Other: warning
  color.output_intent_required:
    enabled: true
    severity: error
    timeout_seconds: 60
  transparency.live_transparency_policy:
    enabled: true
    severity: warning
    severity_by_feature:
      stroking_alpha: warning
      non_stroking_alpha: warning
      soft_mask: warning
      blend_mode: warning
      transparency_group: warning
    timeout_seconds: 60
  geometry.page_boxes_present:
    enabled: true
    severity: error
    required_boxes:
      - MediaBox
      - TrimBox
      - BleedBox
  geometry.trim_size_matches:
    enabled: true
    severity: error
    expected_width_pt: 612
    expected_height_pt: 792
    tolerance_pt: 0.5
  geometry.bleed_margin_at_least:
    enabled: true
    severity: error
    margin_pt: 9
    tolerance_pt: 0.5
  geometry.object_bounds_within_box:
    enabled: true
    severity: warning
    box: BleedBox
    tolerance_pt: 0.5
```

Severity levels:

- `info`
- `warning`
- `error`

## Notes

- Output is JSON written to the required `--output` path.
- Logs are written to stderr.
- The JSON format is not stable yet.
- Raw Ghostscript logs are not included in output.
- Image effective resolution and image color-space policy checks cover page content and nested Form XObject content.
- Print target requires an OutputIntent; ebook target disables that requirement.
- Transparency policy checks cover applied graphics states and directly used transparency-group XObjects in page and Form XObject content.
- Structural bleed checks compare BleedBox margins against TrimBox; they do not verify that artwork visually fills the bleed area.
- Object bounds checks currently cover placed images and Form XObjects, not text, vector paths, annotations, patterns, or raster-derived artwork.
- `summary.color.image_color_space_findings_by_family` counts color policy findings, not all allowed image color spaces.
- `uv.lock` should be committed for reproducible CLI and CI behavior.
