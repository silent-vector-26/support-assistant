"""Write validated optional ARM parameters without logging deployment secrets."""

from datetime import date
import json
import os
from pathlib import Path
import re
import sys
from typing import Mapping
from urllib.parse import urlsplit


def build_parameters(env: Mapping[str, str]) -> dict:
    enabled = env.get("AI_EXPLANATIONS_ENABLED", "").strip().lower() or "false"
    if enabled not in {"true", "false"}:
        raise ValueError("AI_EXPLANATIONS_ENABLED must be true or false.")
    parameters = {"aiExplanationsEnabled": {"value": enabled == "true"}}
    if enabled == "true":
        for setting, parameter in (
            ("AZURE_OPENAI_ENDPOINT", "openAiEndpoint"),
            ("AZURE_OPENAI_DEPLOYMENT", "openAiDeployment"),
            ("AZURE_OPENAI_KEY", "openAiKey"),
        ):
            value = env.get(setting, "").strip()
            if not value:
                raise ValueError(f"{setting} is required when AI explanations are enabled.")
            parameters[parameter] = {"value": value}
        endpoint = urlsplit(parameters["openAiEndpoint"]["value"])
        if (
            endpoint.scheme != "https" or not endpoint.hostname
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment
            or endpoint.path not in {"", "/"}
        ):
            raise ValueError("AZURE_OPENAI_ENDPOINT must be an HTTPS resource endpoint.")

    amount = env.get("BUDGET_AMOUNT", "").strip() or "0"
    if not re.fullmatch(r"[0-9]+", amount):
        raise ValueError("BUDGET_AMOUNT must be a non-negative integer.")
    parameters["budgetAmount"] = {"value": int(amount)}
    if int(amount) > 0:
        start = env.get("BUDGET_START_DATE", "").strip()
        try:
            parsed = date.fromisoformat(start)
        except ValueError:
            raise ValueError("BUDGET_START_DATE must use yyyy-MM-01.") from None
        if parsed.day != 1 or parsed.isoformat() != start:
            raise ValueError("BUDGET_START_DATE must use yyyy-MM-01.")
        try:
            emails = json.loads(env.get("BUDGET_CONTACT_EMAILS", ""))
        except ValueError:
            raise ValueError("BUDGET_CONTACT_EMAILS must be a JSON array of addresses.") from None
        if not isinstance(emails, list) or not emails or any(
            not isinstance(email, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
            for email in emails
        ):
            raise ValueError("BUDGET_CONTACT_EMAILS must be a non-empty array of addresses.")
        parameters["budgetStartDate"] = {"value": start}
        parameters["budgetContactEmails"] = {"value": emails}
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
        "contentVersion": "1.0.0.0",
        "parameters": parameters,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("Usage: deployment_settings.py OUTPUT_PATH", file=sys.stderr)
        return 2
    try:
        settings = build_parameters(os.environ)
    except ValueError as exc:
        print(f"Invalid deployment configuration: {exc}", file=sys.stderr)
        return 1
    path = Path(argv[0])
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(settings, output)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
