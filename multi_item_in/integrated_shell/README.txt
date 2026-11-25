Project Desktop — standalone UI scaffold

Install:
  py -m pip install -r requirements.txt

Run:
  py main.py

The app creates config.json and history.json in its own folder automatically.

Included:
- Native PySide6 desktop window
- Grid-based layout
- Editable settings and JSON persistence
- Manual clipboard preview/paste
- Local history
- Window size persistence

This UI scaffold is intentionally not wired into gameplay automation or its start/stop loop.
