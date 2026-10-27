"""Plan and optionally apply a conservative Azure Container Registry image cleanup.

Dry-run is the default and deletes nothing. Deletion requires --apply.
The running image and the newest --keep tags (rollback images) are always preserved,
as is any digest still referenced by a preserved tag.

Examples:
  python scripts/acr_cleanup.py --registry <name> --app <app> --resource-group <rg>
  python scripts/acr_cleanup.py --registry <name> --app <app> --resource-group <rg> --keep 5 --apply
"""

import argparse
import json
import subprocess
import sys

REPOSITORY = "field-tech-copilot"


def plan_cleanup(manifests, running_tag, keep):
    """Return (preserved, deletable) lists of manifest dicts.

    manifests need "digest", "tags" (list) and "lastUpdateTime" (ISO-8601 string).
    Untagged manifests that no preserved tag references are deletable.
    """
    if keep < 1:
        raise ValueError("keep must be at least 1")
    if not running_tag:
        raise ValueError("The running image tag is required; refusing to plan deletions without it")
    ordered = sorted(manifests, key=lambda m: m["lastUpdateTime"], reverse=True)
    if not any(running_tag in (m.get("tags") or []) for m in ordered):
        raise ValueError(f"Running tag {running_tag!r} was not found in the registry; refusing to plan deletions")
    preserved_digests = set()
    rollbacks = 0
    for manifest in ordered:
        tags = manifest.get("tags") or []
        if running_tag in tags:
            preserved_digests.add(manifest["digest"])
        elif tags and rollbacks < keep:
            rollbacks += 1
            preserved_digests.add(manifest["digest"])
    preserved = [m for m in ordered if m["digest"] in preserved_digests]
    deletable = [m for m in ordered if m["digest"] not in preserved_digests]
    return preserved, deletable


def az(*args):
    result = subprocess.run(["az", *args], capture_output=True, text=True, shell=sys.platform == "win32")
    if result.returncode != 0:
        raise SystemExit(f"az {' '.join(args[:3])} failed: {result.stderr.strip()}")
    return result.stdout


def running_tag_for(app, resource_group):
    image = az("containerapp", "show", "-n", app, "-g", resource_group,
               "--query", "properties.template.containers[0].image", "-o", "tsv").strip()
    if ":" not in image.rsplit("/", 1)[-1]:
        raise SystemExit(f"Cannot determine a tag from running image {image!r}")
    return image.rsplit(":", 1)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--app", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--keep", type=int, default=3, help="Rollback tagged images to keep besides the running one")
    parser.add_argument("--apply", action="store_true", help="Delete the listed manifests (default is dry-run)")
    args = parser.parse_args()

    running = running_tag_for(args.app, args.resource_group)
    manifests = json.loads(az("acr", "manifest", "list-metadata", "-r", args.registry,
                              "-n", REPOSITORY, "-o", "json"))
    preserved, deletable = plan_cleanup(manifests, running, args.keep)

    print(f"Running tag: {running}")
    print("Preserved:")
    for m in preserved:
        print(f"  KEEP   {m['digest'][:19]} {','.join(m.get('tags') or [])}")
    print("Deletable:")
    for m in deletable:
        print(f"  DELETE {m['digest'][:19]} {','.join(m.get('tags') or ['<untagged>'])}")
    if not deletable:
        print("  (none)")
    if not args.apply:
        print("Dry run only. Re-run with --apply to delete the manifests listed above.")
        return
    for m in deletable:
        az("acr", "repository", "delete", "-n", args.registry,
           "--image", f"{REPOSITORY}@{m['digest']}", "--yes")
        print(f"Deleted {m['digest']}")


if __name__ == "__main__":
    main()
