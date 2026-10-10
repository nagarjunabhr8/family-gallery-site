# Run every test: backend unit tests (with coverage), frontend type-check/build, and Playwright E2E.
#   powershell -ExecutionPolicy Bypass -File scripts\test_all.ps1
# Uses only generated sample photos and throwaway data folders; your library and data\ are not touched.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

Write-Host "`n== Backend: pytest ==" -ForegroundColor Cyan
Push-Location (Join-Path $root 'backend')
& .\.venv\Scripts\python -m pytest -q -p no:warnings --cov=app --cov-report=term:skip-covered
if ($LASTEXITCODE -ne 0) { $failed += 'backend' }
Pop-Location

Write-Host "`n== Frontend: type-check + build ==" -ForegroundColor Cyan
Push-Location (Join-Path $root 'frontend')
npm run build --silent
if ($LASTEXITCODE -ne 0) { $failed += 'frontend' }
Pop-Location

Write-Host "`n== E2E: Playwright (desktop + phone + read-only proof) ==" -ForegroundColor Cyan
Push-Location (Join-Path $root 'e2e')
$env:FM_E2E_SKIP_BUILD = '1'  # just built above
npx playwright test
if ($LASTEXITCODE -ne 0) { $failed += 'e2e' }
Remove-Item Env:FM_E2E_SKIP_BUILD
Pop-Location

if ($failed.Count) {
    Write-Host "`nFAILED: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "`nAll tests passed." -ForegroundColor Green
