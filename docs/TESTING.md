# Testing

## Core and UI-logic regressions

Install the runtime dependencies, then run:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

This suite covers deterministic core behavior and Streamlit AppTest report synchronization. It does not launch a browser. The browser directory deliberately has no `__init__.py`, so this command does not require Playwright or include the separate acceptance suite.

## Browser acceptance tests

Use Python 3.10+ from the repository root:

```powershell
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python -m unittest discover -s tests/browser -v
```

On Linux CI, install browser system dependencies with `python -m playwright install --with-deps chromium`. Chromium installation downloads the browser; it is not part of the production container.

Each test launches an isolated local Streamlit process on an available loopback port and uses a fresh Chromium context. The harness waits for HTTP health before interacting and stops its own process/browser on completion. No existing development server or Azure credentials are required. The tests remove inherited Vision credentials from the child process. The OCR error scenario uses a local synthetic HTTP 503 server, not Azure.

Scenarios:

- Create a case, inspect cited guidance, record a documented check, edit and review the report, add evidence, reconcile preserved edits and verify the downloaded Markdown and reviewed filename.
- Display unsupported and unsafe-question responses without documented checks.
- Upload a synthetic image and verify visible missing-OCR-configuration behavior.
- Upload a synthetic image and verify a simulated OCR service error without creating confirmed observations.

These are deterministic acceptance checks against the local app, not live Azure/model availability tests. They do not prove all real OCR responses, every browser version, or production workload behavior.

## Diagnostics and CI

The harness writes Streamlit logs, screenshots and Playwright traces to ignored `test-results/browser/`. Diagnostics are captured on successful runs too, so evidence of the final UI is available alongside failure investigation. Trace capture starts before navigation. If setup fails before the browser opens, the Streamlit log may be the only artifact.

Open a trace locally:

```powershell
python -m playwright show-trace test-results/browser/test_complete_case_report_and_reconciliation.zip
```

Use synthetic data only. Trace snapshots and screenshots can contain entered data. Do not upload sensitive case information, credentials or private content to a trace viewer or issue.

GitHub Actions runs **Browser acceptance tests** alongside **Test application and validate Bicep** for PRs targeting `main`, relevant `main` pushes and manual dispatch. The browser job has no Azure environment credentials. Its diagnostics are uploaded even on failure and retained for seven days. Deployment depends on both jobs succeeding and still requires the `azure-production` approval gate. If branch protection uses required checks, administrators should also require **Browser acceptance tests**.
