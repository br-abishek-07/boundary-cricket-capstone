# Startup import fix — 18 October 2026

The hosted screenshot shows an ImportError at the app's analytics import. The original exception detail is hidden by Streamlit. Loading the previous release's `analytics` module into Python's module cache reproduces the same startup failure locally: the newer functions cannot be imported.

The application now imports its helpers from the `boundary_core` package. Internal imports are relative; data, assets and runtime paths resolve to the repository root. The app does not remove or reload unrelated installed modules. Generic top-level analytics, agent, storage and branding files are removed. The root `prediction.py` remains a command-line wrapper for rebuilding the packaged model. Altair is now explicitly declared as a direct dependency.

A clean virtual environment was installed from requirements.txt. The analytical and full workflow suites were rerun, and startup regressions cover cached generic modules, evidence-tool reruns, a different launch directory and packaged resource paths. Actual results are in data/startup_checks.json, data/startup_browser_checks.json and data/release_checks.json. This reproduces and corrects the observed failure pattern; the exact hosted exception cannot be confirmed without the hosted logs.

Streamlit settings remain repository main / app.py. Existing hosting secrets remain private and do not need to be copied into source. A dependency change causes an environment rebuild. If the old error remains after the update, use Manage app > Reboot app to restart the hosted process. A browser refresh alone does not clear server-side Python modules.
