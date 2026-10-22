# Using the OriginScan GitHub Action

> Add OriginScan to your pull request workflow to automatically scan
> diffs for vulnerabilities with context-adaptive depth.

## Quick Start

Add this workflow to `.github/workflows/originscan.yml`:

```yaml
name: OriginScan PR Scan
on:
  pull_request:
    types: [opened, synchronize]

permissions:
  contents: read
  pull-requests: write

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Required for full diff and provenance

      - uses: ./action
        with:
          fail-on-findings: 'false'
```

## How It Works

1. **Install**: The action installs OriginScan from its own repo (`${{ github.action_path }}/..`), not the scanned repo.
2. **Diff**: Generates a diff between the PR base and head commits.
3. **Scan**: Runs `originscan scan` with the diff, writing reports to a temp directory.
4. **Comment**: Posts (or updates) a PR comment with the Markdown report.
5. **Exit**: Returns the scan's exit code after posting the comment.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `repo-path` | No | `.` | Path to the repository being scanned |
| `policy` | No | - | Path to `policy.yaml` |
| `budget` | No | - | Per-PR token budget cap |
| `format` | No | `json,md` | Output formats (json, md, or json,md) |
| `fail-on-findings` | No | `false` | Exit 1 if any findings |
| `dry-run` | No | `false` | Print comment instead of posting |
| `github-token` | No | `${{ github.token }}` | Token for PR comments |

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Scan completed, no actionable findings |
| `1` | Findings detected (only with `--fail-on-findings`) |
| `2` | Usage or runtime error |

The comment is always posted/printed **before** the action exits, so the PR
comment is visible even when the action fails.

## API Keys

If using real LLM detectors, add API keys as repository secrets:

```yaml
- uses: ./action
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

## Dry Run Mode

To test without posting comments:

```yaml
- uses: ./action
  with:
    dry-run: 'true'
```

The comment body will be printed to stdout.

## Comment Updates

OriginScan uses a hidden HTML marker (`<!-- originscan -->`) in its
comments. When you push new commits to the PR, the action updates the
existing comment instead of creating a new one.

## Report Files

The scan writes reports to a temporary directory (`/tmp/originscan_out/`):
- `report.json` — structured JSON with metadata, findings, and token stats
- `report.md` — Markdown PR comment body

Which files are written depends on `--format` (default: `json,md`).

## Requirements

- **`fetch-depth: 0`** in the checkout step (for full git history and provenance)
- **`pull-requests: write`** permission (for posting comments)
- The action installs OriginScan automatically; no separate install step needed
