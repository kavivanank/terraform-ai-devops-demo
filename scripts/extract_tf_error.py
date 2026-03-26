#!/usr/bin/env python3
"""
extract_tf_error.py
====================
Runs inside GitHub Actions after a terraform failure.
Reads the raw log, extracts structured errors, and outputs
a clean JSON file that gets POSTed to Make.com webhook.

Make.com receives ready-to-use fields — no Text Parser needed.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def extract_errors(log_text: str) -> list[dict]:
    """Extract structured errors from terraform output."""
    errors = []

    # Box-drawing error blocks: ╷ │ Error: ... ╵
    box_re = re.compile(
        r"╷\s*\n│\s*Error:\s*(.*?)\n(│.*?)(?=╵)",
        re.DOTALL
    )
    for m in box_re.finditer(log_text):
        title = m.group(1).strip()
        body = "\n".join(
            re.sub(r"^│\s*", "", line).strip()
            for line in m.group(2).split("\n")
            if line.strip()
        )
        error = {"title": title, "detail": body, "file": None, "line": None, "resource": None}

        ref = re.search(r"on\s+([\w./]+)\s+line\s+(\d+)(?:,\s+in\s+(.+?))?(?:\n|:)", body)
        if ref:
            error["file"] = ref.group(1)
            error["line"] = int(ref.group(2))
            error["resource"] = ref.group(3).strip() if ref.group(3) else None
        errors.append(error)

    # Fallback: simple Error: lines
    if not errors:
        for m in re.finditer(r"Error:\s*(.+?)(?:\n\n|\Z)", log_text, re.DOTALL):
            errors.append({
                "title": m.group(1).strip()[:200],
                "detail": m.group(1).strip(),
                "file": None, "line": None, "resource": None,
            })

    # State lock
    if re.search(r"Error\s+(?:acquiring|releasing)\s+the\s+state\s+lock", log_text, re.I):
        errors.append({
            "title": "State lock conflict",
            "detail": "Another terraform process may hold the lock.",
            "file": None, "line": None, "resource": "terraform.tfstate",
        })

    return errors


def extract_warnings(log_text: str) -> list[str]:
    """Extract warning titles."""
    return [
        m.group(1).strip()
        for m in re.finditer(r"╷\s*\n│\s*Warning:\s*(.*?)\n", log_text)
    ][:5]


def build_error_summary(errors, warnings, stage):
    """Pre-formatted text block ready for LLM prompt."""
    lines = [f"Terraform {stage} failed with {len(errors)} error(s):\n"]
    for i, e in enumerate(errors, 1):
        lines.append(f"--- Error {i} ---")
        lines.append(f"Title: {e['title']}")
        if e["detail"] and e["detail"] != e["title"]:
            lines.append(f"Detail: {e['detail']}")
        if e["file"]:
            loc = f"{e['file']}:{e['line']}" if e["line"] else e["file"]
            lines.append(f"Location: {loc}")
        if e["resource"]:
            lines.append(f"Resource: {e['resource']}")
        lines.append("")
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"  - {w}" for w in warnings)
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", required=True, choices=["init", "plan", "apply"])
    p.add_argument("--log-file", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--repo", default="")
    p.add_argument("--sha", default="")
    p.add_argument("--branch", default="")
    p.add_argument("--run-id", default="")
    args = p.parse_args()

    log_path = Path(args.log_file)
    if not log_path.exists():
        print(f"ERROR: Log file not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    log_text = log_path.read_text(errors="replace")
    errors = extract_errors(log_text)
    warnings = extract_warnings(log_text)

    if not errors:
        errors = [{
            "title": f"Unrecognized error during terraform {args.stage}",
            "detail": "Could not parse error blocks. See raw log.",
            "file": None, "line": None, "resource": None,
        }]

    payload = {
        "stage": args.stage,
        "repository": args.repo,
        "commit_sha": args.sha,
        "branch": args.branch,
        "run_id": args.run_id,
        "error_count": len(errors),
        "errors": errors,
        "warnings": warnings,
        "error_summary": build_error_summary(errors, warnings, args.stage),
    }

    Path(args.output).write_text(json.dumps(payload, indent=2))
    print(f"Extracted {len(errors)} error(s), {len(warnings)} warning(s)")
    for i, e in enumerate(errors, 1):
        loc = f" ({e['file']}:{e['line']})" if e.get("file") else ""
        print(f"  [{i}] {e['title'][:80]}{loc}")


if __name__ == "__main__":
    main()
