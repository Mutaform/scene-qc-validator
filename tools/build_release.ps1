$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$addonDir = Join-Path $repoRoot "scene_qc_validator"
$manifest = Join-Path $addonDir "blender_manifest.toml"
$distDir = Join-Path $repoRoot "dist"
$zipPath = Join-Path $distDir "scene_qc_validator_by_mutaform_studio.zip"

if (-not (Test-Path -LiteralPath $manifest)) {
    throw "Missing blender_manifest.toml in $addonDir"
}

if (Test-Path -LiteralPath $distDir) {
    Remove-Item -LiteralPath $distDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$stagingAddon = Join-Path $distDir "_stage"
New-Item -ItemType Directory -Force -Path $stagingAddon | Out-Null

Copy-Item -LiteralPath (Join-Path $addonDir "*") -Destination $stagingAddon -Recurse -Force

Get-ChildItem -LiteralPath $stagingAddon -Directory -Recurse -Filter "__pycache__" |
    Remove-Item -Recurse -Force

Get-ChildItem -LiteralPath $stagingAddon -File -Recurse |
    Where-Object {
        $_.Extension -in @(".pyc", ".pyo") -or
        $_.Name -in @(".DS_Store", "Thumbs.db") -or
        $_.Name -match "\.blend\d+$"
    } |
    Remove-Item -Force

Compress-Archive -Path (Join-Path $stagingAddon "*") -DestinationPath $zipPath -Force
Remove-Item -LiteralPath $stagingAddon -Recurse -Force

Write-Host "Built $zipPath"
