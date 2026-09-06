#!/usr/bin/env python3
"""Fetch reviewed GitHub sources and publish deterministic, attributed rule sets.

SPDX-License-Identifier: GPL-3.0-only
Copyright (C) 2026 SarinV
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
MAX_DOWNLOAD = 2_000_000
DOMAIN_RE = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$")
RETRY_HTTP = {408, 429, 500, 502, 503, 504}


class UpdateError(ValueError):
    pass


class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        before, after = urlparse(request.full_url), urlparse(new_url)
        if (after.scheme, after.netloc) != (before.scheme, before.netloc):
            raise UpdateError("Unexpected cross-origin redirect")
        return super().redirect_request(request, fp, code, msg, headers, new_url)


urlopen = build_opener(SameOriginRedirect()).open


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def download(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"api.github.com", "raw.githubusercontent.com"}:
        raise UpdateError("Only HTTPS GitHub API/raw sources are allowed")
    headers = {"User-Agent": "SarinV-honor-of-kings-rules", "Accept": "application/vnd.github+json"}
    # The token is used only for GitHub API quota, never for raw file downloads.
    if parsed.hostname == "api.github.com" and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=30) as response:
                if urlparse(response.url).hostname != parsed.hostname:
                    raise UpdateError("Unexpected cross-host redirect")
                data = response.read(MAX_DOWNLOAD + 1)
            if not data or len(data) > MAX_DOWNLOAD:
                raise UpdateError("Empty or oversized upstream response")
            data.decode("utf-8-sig")
            return data
        except HTTPError as exc:
            if exc.code not in RETRY_HTTP or attempt == 2:
                raise UpdateError(f"Upstream HTTP {exc.code}: {url}") from None
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise UpdateError(f"Upstream download failed: {url} ({type(exc).__name__})") from None
        time.sleep(2 ** attempt)
    raise UpdateError("Download retries exhausted")


def api(path):
    return json.loads(download("https://api.github.com/" + path))


def parse_rules(text, format_name):
    records = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.lstrip("\ufeff").split("#", 1)[0].strip()
        if not line or line.startswith("//"):
            continue
        if "<html" in line.lower() or "<!doctype" in line.lower():
            raise UpdateError("HTML received instead of a rule file")
        if format_name == "classical":
            parts = [part.strip() for part in line.split(",")]
            if len(parts) not in (2, 3):
                raise UpdateError(f"Invalid classical rule on line {line_number}")
            kind, value = parts[:2]
            kind = kind.upper()
            if kind not in {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6"}:
                raise UpdateError(f"Unsupported classical rule type on line {line_number}: {kind}")
            if len(parts) == 3 and (kind not in {"IP-CIDR", "IP-CIDR6"} or parts[2] != "no-resolve"):
                raise UpdateError(f"Unexpected policy/option in upstream on line {line_number}")
        elif format_name == "geosite":
            # Attributes are metadata. Includes/regex are recorded but never expanded.
            fields = line.split()
            if any(not attr.startswith("@") for attr in fields[1:]):
                raise UpdateError(f"Invalid geosite attributes on line {line_number}")
            item = fields[0]
            if ":" in item:
                prefix, value = item.split(":", 1)
                mapping = {"full": "DOMAIN", "domain": "DOMAIN-SUFFIX", "keyword": "DOMAIN-KEYWORD", "regexp": "REGEXP", "include": "INCLUDE"}
                if prefix not in mapping:
                    raise UpdateError(f"Unsupported geosite prefix on line {line_number}: {prefix}")
                kind = mapping[prefix]
            else:
                kind, value = "DOMAIN-SUFFIX", item
        else:
            raise UpdateError(f"Unknown source format: {format_name}")
        value = value.lower()
        if not value:
            raise UpdateError(f"Empty rule value on line {line_number}")
        if kind in {"DOMAIN", "DOMAIN-SUFFIX"} and not DOMAIN_RE.fullmatch(value):
            raise UpdateError(f"Invalid domain on line {line_number}: {value}")
        records.append({"line": line_number, "raw": raw, "type": kind, "value": value})
    if not records:
        raise UpdateError("Source contains no rules")
    return records


def select_rules(source, records, policy):
    accepted, excluded = [], []
    for record in records:
        kind, value = record["type"], record["value"]
        reason = None
        profile = "standard"
        if kind not in {"DOMAIN", "DOMAIN-SUFFIX"}:
            reason = "IP ranges, keyword, regex and include rules require separate review; no automatic conversion."
        elif value in policy["excluded_suffixes"]:
            reason = policy["excluded_suffixes"][value]
        elif source["selection"] == "shared-services":
            if kind != "DOMAIN-SUFFIX" or value not in policy["shared_service_suffixes"]:
                reason = "Not in the reviewed shared-service selection."
            else:
                profile = "extended-only"
        elif source["selection"] != "dedicated-game":
            raise UpdateError("Unknown source selection")
        if reason:
            excluded.append({**record, "reason": reason})
        else:
            accepted.append({**record, "rule": f"{kind},{value}", "profile": profile})
    if len(accepted) < source["min_selected"]:
        raise UpdateError(f"Source {source['id']} has too few usable rules; preserving published files")
    return accepted, excluded


def fetch_source(source, root, now, stale_days):
    repo, ref = source["repository"], source["ref"]
    metadata = api(f"repos/{repo}")
    if metadata.get("archived") or metadata.get("disabled"):
        raise UpdateError(f"Source {repo} is archived or disabled")
    if (metadata.get("license") or {}).get("spdx_id") != source["license"]:
        raise UpdateError(f"Source {repo} license changed; review before updating")
    head = api(f"repos/{repo}/commits/{quote(ref, safe='')}")
    revision = head["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise UpdateError("Invalid upstream revision")
    pushed_at = metadata["pushed_at"]
    if (now - datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))).days > stale_days:
        raise UpdateError(f"Source {repo} has had no repository activity for over {stale_days} days")
    query = urlencode({"sha": revision, "path": source["path"], "per_page": 1})
    commits = api(f"repos/{repo}/commits?{query}")
    if not commits:
        raise UpdateError(f"Missing source file history: {source['id']}")
    raw_url = f"https://raw.githubusercontent.com/{repo}/{revision}/{quote(source['path'], safe='/')}"
    license_url = f"https://raw.githubusercontent.com/{repo}/{revision}/{quote(source['license_path'], safe='/')}"
    content = download(raw_url)
    license_data = download(license_url)
    approved_license = root / "licenses" / (source["id"] + ".txt")
    if not approved_license.exists() or approved_license.read_bytes() != license_data:
        raise UpdateError(f"Upstream license differs from reviewed copy: {source['id']}")
    status = {
        "id": source["id"], "repository": repo, "ref": ref, "path": source["path"],
        "commit": revision, "repository_pushed_at": pushed_at,
        "file_commit": commits[0]["sha"], "file_updated_at": commits[0]["commit"]["committer"]["date"],
        "stars_at_check": metadata["stargazers_count"], "license": source["license"],
        "license_sha256": sha256(license_data), "sha256": sha256(content),
        "url": f"https://github.com/{repo}/blob/{revision}/{source['path']}",
        "raw_url": raw_url,
    }
    return source, content, status


def build_outputs(bundles, policy):
    standard, extended = set(), set()
    provenance = defaultdict(list)
    source_reports = []
    for source, content, metadata in bundles:
        records = parse_rules(content.decode("utf-8-sig"), source["format"])
        accepted, excluded = select_rules(source, records, policy)
        for record in accepted:
            rule = record["rule"]
            extended.add(rule)
            if record["profile"] == "standard":
                standard.add(rule)
            provenance[rule].append({"source": source["id"], "line": record["line"], "raw": record["raw"], "profile": record["profile"]})
        source_reports.append({"id": source["id"], "parsed_count": len(records), "selected_count": len(accepted), "excluded": excluded})
    if not set(policy["required_rules"]).issubset(standard):
        raise UpdateError("Required HOK rules disappeared; preserving published files")
    for rules in (standard, extended):
        if not rules or len(rules) > policy["max_rules_per_profile"]:
            raise UpdateError("Unexpected rule count; preserving published files")
    outputs = {}
    profiles = {"HonorOfKings": sorted(standard), "HonorOfKings-Extended": sorted(extended)}
    for name, rules in profiles.items():
        header = (
            f"# {name} - Honor of Kings Global\n"
            "# SPDX-License-Identifier: GPL-3.0-only\n"
            "# Derived and filtered from credited upstreams; modified by SarinV.\n"
            "# Sources, original notices and exclusions: ../data/provenance.json, ../upstream/, ../NOTICE.md\n"
            f"# Total: {len(rules)}; behavior: classical; no routing policy embedded.\n"
        )
        if name.endswith("Extended"):
            header += "# Includes shared Tencent game services; affects other games using those domains.\n"
        outputs[f"rules/{name}.yaml"] = (header + "payload:\n" + "".join(f"  - '{rule}'\n" for rule in rules)).encode("utf-8")
        outputs[f"rules/{name}.list"] = (header + "\n".join(rules) + "\n").encode("utf-8")
    outputs["data/provenance.json"] = json_bytes({"schema_version": 1, "rules": dict(provenance), "source_selections": source_reports})
    return outputs, profiles


def check_removals(root, profiles, policy):
    for name, rules in profiles.items():
        path = root / "rules" / f"{name}.list"
        if not path.exists():
            continue
        old = {line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")}
        removed = old - set(rules)
        # Check actual removals, not just net count: additions must not hide a mass deletion.
        if old and len(removed) / len(old) > policy["max_removal_fraction"]:
            raise UpdateError(f"Too many removed rules in {name}: {len(removed)}/{len(old)}; review upstream change")


def run(root=ROOT, offline=False, check=False, fetcher=fetch_source):
    source_config = json.loads((root / "sources.json").read_text(encoding="utf-8"))
    policy = json.loads((root / "policy.json").read_text(encoding="utf-8"))
    sources = source_config["sources"]
    now = datetime.now(timezone.utc)
    if offline:
        status = json.loads((root / "data/status.json").read_text(encoding="utf-8"))
        metadata_by_id = {item["id"]: item for item in status["sources"]}
        bundles = []
        for source in sources:
            metadata = metadata_by_id[source["id"]]
            for field in ("repository", "ref", "path", "license"):
                if metadata[field] != source[field]:
                    raise UpdateError("Snapshot does not match configured source; run an online update")
            content = (root / "upstream" / (source["id"] + ".txt")).read_bytes()
            if sha256(content) != metadata["sha256"]:
                raise UpdateError("Cached upstream digest mismatch")
            license_data = (root / "licenses" / (source["id"] + ".txt")).read_bytes()
            if sha256(license_data) != metadata["license_sha256"]:
                raise UpdateError("Cached license digest mismatch")
            bundles.append((source, content, metadata))
    else:
        with ThreadPoolExecutor(max_workers=len(sources)) as pool:
            futures = [pool.submit(fetcher, source, root, now, policy["repository_stale_days"]) for source in sources]
            # No file writes occur until EVERY source download, parse and validation succeeds.
            bundles = [future.result() for future in futures]
    outputs, profiles = build_outputs(bundles, policy)
    check_removals(root, profiles, policy)
    if offline:
        if status["counts"] != {name: len(rules) for name, rules in profiles.items()}:
            raise UpdateError("Snapshot counts do not match generated rules")
    else:
        status = {
            "schema_version": 1, "last_successful_check_utc": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "counts": {name: len(rules) for name, rules in profiles.items()},
            "sources": [bundle[2] for bundle in bundles],
            "meaning": "All sources fetched and validated. This is not a new-rule timestamp or a gameplay test.",
        }
        outputs["data/status.json"] = json_bytes(status)
        for source, content, _ in bundles:
            outputs[f"upstream/{source['id']}.txt"] = content
    changed = [name for name, content in outputs.items() if not (root / name).exists() or (root / name).read_bytes() != content]
    if check and changed:
        raise UpdateError("Generated files are out of date: " + ", ".join(changed))
    if not check:
        for name in changed:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_bytes(outputs[name])
            temporary.replace(path)
    print(json.dumps({"counts": status["counts"], "changed_files": changed, "mode": "offline-check" if check else "update"}))
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Rebuild only from hash-checked committed source snapshots")
    parser.add_argument("--check", action="store_true", help="Fail if generated files differ; implies --offline and makes no writes")
    args = parser.parse_args()
    try:
        run(offline=args.offline or args.check, check=args.check)
    except (UpdateError, KeyError, UnicodeError, json.JSONDecodeError, OSError) as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
