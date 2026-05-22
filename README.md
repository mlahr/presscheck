# PDFdancer Preflight

Architecture prototype for an internal, CI-oriented PDF preflight tool.

Run:

```bash
uv run pdfdancer-preflight --target examples/targets/print-basic.yml input.pdf
```

The CLI writes JSON to stdout and exits nonzero when findings meet or exceed the target's `fail_at` severity.

