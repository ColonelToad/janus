# `tools/`

Build-time code generation and developer utilities.

- `gen_isa.py` — generates `src/isa_pkg.sv` and `docs/isa.md` from `isa/isa.yaml`

```sh
python tools/gen_isa.py          # regenerate
python tools/gen_isa.py --check  # verify committed files are current (CI)
```

Planned additions: trace and coverage helpers.
