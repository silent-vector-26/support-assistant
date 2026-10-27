# Cost optimization

## Scope and baseline

This guide covers the current Bicep deployment, not a live billing audit. No budgets, resource resizing, retention changes or deletions are applied by adding this document. Prices, grants and actual spend must be checked for the subscription, region and billing agreement before acting.

| Cost driver | Current design | Important boundary |
|---|---|---|
| Container Registry | Basic, always provisioned | Historical estimate about USD 5.10/month, not a current quote or total monthly cap |
| Container Apps | Consumption, 0.5 vCPU / 1 GiB, 0-1 replicas | Active sessions, traffic and cold starts can consume billable usage |
| Log Analytics | PerGB2018, 30-day retention | Ingestion and applicable retention charges vary with volume and plan |
| Vision OCR | Optional external endpoint | Billed separately if configured, not created or included in the baseline |
| GitHub Actions | Linux runners, tests and Docker builds | Private-repository minutes and storage depend on the account plan |
| Network and storage | Image pulls, logs, responses and retained images | Region, traffic, storage allowance and egress affect charges |

Free grants are subject to subscription eligibility and aggregate usage. A maximum of one replica limits capacity, not total spend. An open Streamlit WebSocket can keep a replica active, so scale-to-zero does not guarantee zero compute cost between demonstrations.

## Controls already implemented

- Minimum replicas is zero and maximum is one.
- ACR uses Basic rather than a larger tier.
- Local keyword retrieval has no embedding, search-service or language-model fees.
- OCR runs only on an explicit button click, not every Streamlit rerun.
- Documentation-only pushes do not trigger deployment or its builds. PRs still validate documentation changes alongside code to retain a consistent check.
- Production deployments are serialized and never cancel an active infrastructure deployment.
- The runtime image uses Python slim, and dependencies are installed before application files for reusable Docker layers when a build cache is available. The workflow does not currently configure a persistent Docker cache.

## Prioritized optimization backlog

| Priority | Action | Verification and trade-off |
|---|---|---|
| 1 | Configure an Azure Cost Management budget scoped to the workload resource group with actual and forecast alerts | Choose an owner-approved amount and recipients, verify alert delivery. Budgets alert, they do not stop resources or guarantee a cap |
| 1 | Review daily cost by resource and meter after a representative demo week | Separate registry baseline, compute, logs, network and optional OCR. Account for billing-data delay |
| 1 | Close demo tabs when finished and download reports before idle periods | Verify replicas eventually return to zero. Do not force shutdown while a technician needs session data |
| 2 | Measure console/system log volume and remove excessive application logging | Keep enough data for deployment diagnosis. Never log uploaded images, keys or sensitive case data |
| 2 | Review ACR storage and prune obsolete images under an explicit retention policy | Preserve the running image and chosen rollback images. Do not blindly purge all untagged/old images or assume premium retention features exist in Basic |
| 2 | Add a persistent Docker build cache if measured CI savings justify cache storage | Compare runner duration and cache storage before/after. Never export secrets through layers or cache |
| 2 | Narrow deployment identity RBAC to workload needs | Not a direct price saving, but limits the impact of unintended resource creation. Review subscription deployment and role-assignment requirements first |
| 3 | Load-test a smaller supported CPU/memory allocation | Measure startup time, memory peaks, OCR uploads and interaction latency before changing Bicep. Avoid speculative downsizing |
| 3 | Consider a registry alternative for a public demo image | Compare total cost, pull authentication, rate limits and availability. This changes the ACR requirement and needs an approved design change |
| 3 | Add optional OCR quotas, request deduplication or upload limits if usage increases | Define visible failure behavior and privacy-conscious cache rules. No hidden suppression of OCR requests |

Retention, cache and resource changes should be delivered through reviewed infrastructure/workflow PRs. Budget configuration and subscription RBAC require separate administrative review. No dollar savings are claimed until before/after measurements exist.

## Operational controls

### Budget (disabled until approved)

`infra/main.bicep` can create a resource-group-scoped monthly Cost Management budget with actual (50/80/100%) and forecast (100%) alerts. It is **off by default**: nothing is created unless `budgetAmount` is above 0. Because the amount and recipients are owner decisions, no values are committed. To enable it, the owner supplies:

- `budgetAmount`: monthly amount in the billing currency;
- `budgetStartDate`: the first day of a month, `yyyy-MM-01`;
- `budgetContactEmails`: the approved recipients.

Budgets send notifications only. They are **not spending caps** and do not stop or throttle resources. Cost data lags by hours to a day, so alerts can arrive after spend occurs. After enabling, verify that each recipient receives a test or threshold notification. The deployment identity also needs permission to create budgets on the resource group; review that before granting it.

### ACR cleanup (inspect first)

`scripts/acr_cleanup.py` plans image cleanup for the `field-tech-copilot` repository. It is a **dry run by default** and deletes nothing without `--apply`.

```powershell
python scripts/acr_cleanup.py --registry crfieldtechcopilotdev72c1 --app ca-field-tech-copilot-dev-72c1 --resource-group rg-field-tech-copilot-dev-72c1 [--keep 3] [--apply]
```

It always preserves the image tag currently running in the Container App plus the newest `--keep` tagged images (default 3) as rollback candidates, and any digest referenced by a preserved tag. It refuses to plan deletions if the running tag cannot be determined or is absent from the registry. Unit tests cover these rules. The retention count is a proposed default pending owner approval; deletion is not automated or scheduled.

Observed on 2026-10-27: the registry held 4 tagged images, one running and three rollback candidates, so the dry run found nothing to delete. Image sizes are small, so no storage savings are claimed.

### Findings still to be measured

- **Cost baseline by registry, compute, logs, network and OCR:** not yet recorded. The deployment is only days old and cost data is delayed. Capture it using the measurement procedure below after a representative week, and record the figures here with date, currency and region.
- **Scale-to-zero after sessions close:** not yet verified. Check the replica count metric after closing all demo tabs and waiting through the idle period.
- **Before/after savings:** none claimed.

## Measurement procedure

1. In Azure Cost Management, select the deployment subscription and filter Cost Analysis to `rg-field-tech-copilot-dev-72c1`. Use daily granularity and group by resource, then meter/service.
2. Record a quiet baseline and a representative demo period. Include any separately hosted Vision resource in a second view, since it is outside this resource group.
3. In Container Apps metrics, inspect replica count, CPU, memory and requests around demo periods. Confirm scale-to-zero after closing sessions and allowing the platform's idle period.
4. Inspect Log Analytics usage and ACR storage, and review GitHub Actions minutes/cache storage in GitHub billing.
5. Change one control at a time through a reviewed PR. Repeat the same demo workload and compare spend, startup time, error rate and report usability.

For production-like use, durable case storage and authentication are prerequisites, not optimizations to omit for cost savings. During pauses, deliberate resource teardown can avoid the persistent ACR baseline, but destroys workload resources and must be explicitly authorized after preserving any needed images/logs. Scale-to-zero alone does not remove registry or log charges.

## Review cadence

Review spend weekly during active development and after enabling OCR, changing replica limits or increasing demo traffic. Record the pricing date, region, currency, observed usage and approved follow-up decisions in a future cost review rather than treating the original planning estimate as a bill.

References: [Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/), [Container Apps billing](https://learn.microsoft.com/azure/container-apps/billing), [Cost Management budgets](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets), [GitHub Actions billing](https://docs.github.com/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions).
