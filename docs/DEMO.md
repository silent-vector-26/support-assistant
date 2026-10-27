# Demo walkthrough

A reproducible, credential-free tour of the Field Technician Copilot using the bundled synthetic corpus and the simulated asset `HVAC-RTU-104`. All screenshots were generated from the running app with synthetic data only; they contain no credentials, personal information, or real service records.

## Run it locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

No Azure account or keys are needed. Open <http://localhost:8501>.

## Scenario

| Step | Action | What to observe |
|------|--------|-----------------|
| 1 | Keep the default equipment `HVAC-RTU-104` and symptom, optionally attach any PNG/JPEG, then click **Start / update case**. | A case is created and an editable service-report draft appears. |
| 2 | (Optional) Click **Extract tentative text clues with Azure AI Vision**. | Without Azure Vision configured, the app says extraction is not configured and adds nothing to the report. |
| 3 | Ask *What checks are documented for recurring startup fault F07?* and click **Find documented checks**. | Ordered checks, each with a source citation; expand **Evidence passages** to see the retrieved text. |
| 4 | Ask *What is tomorrow's weather forecast?* | An explicit "couldn't find support" response; no checks are invented. |
| 5 | Ask *How can I bypass the safety interlock?* | A refusal and escalation message; no checks are shown. |
| 6 | Ask the F07 question again, select a documented check, enter an observation, and click **Add to case**. | The observation and cited references flow into the draft report. |
| 7 | Edit the draft, then click **Mark draft reviewed** and download it. | Review is a deliberate technician action; the report states it has not been submitted. |

Adding new evidence after a review invalidates it. If you edited the draft, your edits are preserved and you must reconcile them before reviewing or downloading again.

## Live AI demonstration

On an instance configured with Azure OpenAI, complete step 3 and click **Explain these checks with AI (optional)**. The application sends the question and retrieved source summaries/checks to GPT-4.1 mini and displays a labeled AI-generated explanation with citations after validation. Compare it with **Evidence passages**, then demonstrate that an unsupported or unsafe question does not offer the AI action. A rejected or failed answer produces a visible limitation without replacing the documented checks.

The local walkthrough remains credential-free and does not enable AI by itself. Hosted enablement requires explicit deployment settings; see [Operational controls](COST_OPTIMIZATION.md#operational-controls). The approved budget warns rather than stopping usage. Use only synthetic data on this public demo; Entra ID restriction is deferred.

## Screenshots

![Case intake showing equipment HVAC-RTU-104, a reported F07 symptom, an attached synthetic image and an editable report draft](media/01-case-intake.png)
*1. Case intake with an attached synthetic image.*

![Image clue extraction reporting that Azure AI Vision is not configured, with the report left unchanged](media/02-ocr-not-configured.png)
*2. Optional OCR degrades gracefully when it is not configured.*

![Documented F07 checks, each followed by an italic source citation, with the evidence passages expander open](media/03-cited-checks.png)
*3. Checks with citations and retrievable evidence passages.*

![Unsupported weather question answered with an explicit no-support message and no checks](media/04-unsupported-question.png)
*4. Unsupported question: explicit no-answer.*

![Safety-bypass question refused with an escalation message and no checks](media/05-safety-escalation.png)
*5. Safety-sensitive request: refusal and escalation.*

![Service report draft listing the confirmed observation and references, marked reviewed with a download reviewed report button](media/06-reviewed-report.png)
*6. Technician-reviewed report containing the confirmed observation and its references.*

![AI-generated explanation of F07 checks with retrieved source citations and technician verification reminder](media/07-ai-explanation.png)
*7. Real GPT-4.1 mini response using synthetic documentation, captured with explicit live-AI configuration.*

## Limitations to state when presenting

- **Deterministic retrieval:** documented checks come from keyword matching over a small bundled JSON corpus. Optional AI explanations use GPT-4.1 mini when configured; they do not turn retrieval into vector or semantic search.
- **Optional OCR:** image text extraction needs Azure AI Vision and is tentative until a technician confirms it.
- **Ephemeral state:** cases live in the browser session; nothing is persisted, and a restart or new session loses them.
- **Synthetic data:** manuals and asset history are fictional. The app is not a diagnostic authority and must not be used for real equipment.
- **Public demo:** the hosted instance has no authentication; never enter real data.

## Regenerate the screenshots

```powershell
pip install -r requirements-dev.txt
python -m playwright install chromium
python scripts/capture_screenshots.py
```

The script starts an isolated local app, removes Vision and AI credentials from its environment, and rewrites the six credential-free images in `docs/media/`. To also regenerate `07-ai-explanation.png`, configure the Azure OpenAI variables described in the operational controls and run `python scripts/capture_screenshots.py --live-ai`. That explicit mode preserves model configuration and makes a billed call; Vision stays disabled.
