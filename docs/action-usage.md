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
          fetch-depth: 0  # Required for full diff

      - uses: ./action
        with:
          fail-on-findings: 'false'
```

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `repo-path` | No | `.` | Path to the repository root |
| `policy` | No | - | Path to `policy.yaml` |
| `budget` | No | - | Per-PR token budget cap |
| `format` | No | `json,md` | Output formats |
| `fail-on-findings` | No | `false` | Exit 1 if any findings |
| `dry-run` | No | `false` | Print comment instead of posting |
| `github-token` | No | `${{ github.token }}` | Token for PR comments |

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

## Requirements

- **`fetch-depth: 0`** in the checkout step (for full git history)
- **`pull-requests: write`** permission (for posting comments)
