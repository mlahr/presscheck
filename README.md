# PDFdancer Preflight

Architecture prototype for an internal, CI-oriented PDF preflight tool.

The prototype currently proves the basic flow:

```text
target config -> analyzers -> findings -> severity evaluation -> JSON stdout -> exit code
```

## Requirements

- Python 3.13+
- uv
- Ghostscript available as `gs`
- Java 17+

## Run

Use the sample target config:

```bash
uv run pdfdancer-preflight --target examples/targets/print-basic.yml input.pdf
```

The CLI writes JSON to stdout and exits nonzero when findings meet or exceed the target's `fail_at` severity.

Example with a known PDF:

```bash
uv run pdfdancer-preflight \
  --target examples/targets/print-basic.yml \
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
  uv run pdfdancer-preflight --target examples/targets/print-basic.yml input.pdf
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

Run the Java analyzer tests:

```bash
./gradlew :analyzers:pdfbox:test
```

## Current Checks

- `document_integrity.ghostscript_processable`
- `fonts.non_embedded`
- `geometry.page_boxes_present`
- `geometry.trim_size_matches`

## Target Config

Every run requires a target YAML file. The current format is intentionally small and may change.

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
```

Severity levels:

- `info`
- `warning`
- `error`

## Notes

- Output is JSON on stdout.
- The JSON format is not stable yet.
- Raw Ghostscript logs are not included in output.
- `uv.lock` should be committed for reproducible CLI and CI behavior.
