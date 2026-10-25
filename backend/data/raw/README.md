# Local MCX data files

Put downloaded MCX Bhavcopy CSV files here. Everything in this folder except
this README is ignored by Git, so exchange data is never committed.

Validate a file:

```powershell
cd backend
.venv\Scripts\python.exe -m app.cli import data\raw\<file>.csv
```

See `docs/data-import.md` for supported layouts and validation rules.
