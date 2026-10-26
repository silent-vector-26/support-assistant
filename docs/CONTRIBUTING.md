# Contributing

Thanks for your interest in improving Field Technician Copilot. Contributions should preserve the project's demonstration-only scope, evidence-linked behavior, and safety boundaries.

## Before opening a change

- Open an issue to discuss substantial changes before starting implementation.
- Keep sample equipment, manuals, images, and case records fictional or otherwise explicitly licensed for reuse.
- Do not add credentials, real customer data, private service records, or proprietary manufacturer content.
- Keep the interface clear that this demo is not diagnostic authority and does not control equipment or submit work orders.

## Development checks

Use Python 3.10 or newer, install dependencies from `requirements.txt`, and run these checks from the repository root:

```powershell
python -m unittest discover -s tests -v
python -m py_compile app.py fieldtech_assistant.py tests/test_fieldtech_assistant.py
```

If a change affects infrastructure, also validate the Bicep entry point:

```powershell
az bicep build --file infra/main.bicep --stdout
```

Describe the behavior changed, checks run, and any limitations in the pull request. Keep project documentation in `docs/`, except the root `README.md` and `LICENSE`.
