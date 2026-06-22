#!/usr/bin/env pwsh
# run_checks.ps1 — Full quality gate for the SteamTools project.
# Usage: .\run_checks.ps1
# Exit code 0 = all checks passed. Non-zero = something failed.

$ErrorActionPreference = "Stop"

function Step($label, $cmd) {
    Write-Host "`n==> $label" -ForegroundColor Cyan
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $label" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    Write-Host "OK: $label" -ForegroundColor Green
}

Step "Ruff format check" "uv run ruff format --check ."
Step "Ruff lint"         "uv run ruff check ."
Step "Mypy type check"   "uv run mypy steamtools steamtools_cli steamtools_mcp"
Step "Bandit security"   "uv run bandit -r steamtools steamtools_cli steamtools_mcp --skip B608 -q"
Step "Pytest + coverage" "uv run pytest"

Write-Host "`nAll checks passed." -ForegroundColor Green
