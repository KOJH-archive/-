# Default: inspect only. -CreatePrivate creates only after an empty authenticated repository search.
# Never pushes or overwrites an existing remote. Requires Git and GitHub CLI.
param([switch]$CreatePrivate)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$repo = 'KOJH-archive/korean-legal-research-studio'
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI and run gh auth login first.' }
gh auth status
if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication required.' }
$found = gh repo view $repo --json nameWithOwner,url,isPrivate 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Output $found
    Write-Output 'Repository exists. Inspect its branches before preparing any push.'
    exit 0
}
if (-not $CreatePrivate) { throw 'Repository missing or inaccessible. Check account permissions. Use -CreatePrivate only for a confirmed new repository.' }
# Verify the account and a successful inventory before considering absence established.
$login = gh api user --jq '.login'
if ($LASTEXITCODE -ne 0 -or $login -ne 'KOJH-archive') { throw 'Expected authenticated owner KOJH-archive.' }
$inventory = gh repo list KOJH-archive --limit 1000 --json name --jq '.[].name'
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify repository inventory.' }
if ($inventory -contains 'korean-legal-research-studio') { throw 'Repository exists but is inaccessible. Resolve access first.' }
gh repo create $repo --private --description 'Local Korean legal research with official sources, Ollama, SQLite and Streamlit'
if ($LASTEXITCODE -ne 0) { throw 'Repository creation failed.' }
Write-Output 'Private repository created. No files pushed.'
