# Loading the local agent release

`app.py` obtains its agent functions through `agent_runtime.load_agents()` using the application directory. The loader reads that directory's `agents.py`, captures its bytes, and identifies the release by a hash of the absolute path and content.

Each release uses a private module namespace. An unrelated or older `agents` package in Python's global module cache cannot supply the application's functions. The loader compiles the captured source directly, so stale timestamp-valid bytecode is not reused. Identical source reuses the completed module. Changed source receives a separate module, while callers already using an earlier release keep their original references.

The loader checks all three report functions, all three context-fingerprint functions, and the shared error class before marking the release ready. A failed or incomplete import is not cached as ready. If the optional agent layer cannot load, the app's statistical workspaces remain available and report sections show a controlled availability message.

The OpenAI-compatible SDK remains lazily imported only when a report is requested. Provider requests and JSON validation are unchanged.

Run the focused regression checks from the repository root:

```text
python -m unittest discover -s tests -p "test_*agent*.py" -v
```

The checks cover cached module conflicts, source changes, incomplete releases, statistical fallback and the existing provider/UI contracts. Live Streamlit rebuild status and live model behaviour must be checked separately. After a deployment, use the dev app's Manage app → Reboot if it continues to display an earlier startup error.
