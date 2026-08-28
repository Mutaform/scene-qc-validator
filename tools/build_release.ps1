$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$addonDir = Join-Path $repoRoot "scene_qc_validator"
$manifest = Join-Path $addonDir "blender_manifest.toml"
# Build output. On CI it has to be the repository root, because the workflow
# publishes from the checkout. Locally it goes to the project's Dev folder
# beside the repository, so the working copy holds only the files that are
# actually in the repository.
if ($env:GITHUB_ACTIONS -eq 'true') {
    $outRoot = $repoRoot
} else {
    $outRoot = Join-Path (Split-Path -Parent $repoRoot) "Dev"
    if (-not (Test-Path -LiteralPath $outRoot)) {
        New-Item -ItemType Directory -Force -Path $outRoot | Out-Null
    }
}
$distDir = Join-Path $outRoot "dist"
$zipPath = Join-Path $distDir "scene_qc_validator_by_mutaform_studio.zip"

if (-not (Test-Path -LiteralPath $manifest)) {
    throw "Missing blender_manifest.toml in $addonDir"
}

$version = (Select-String -LiteralPath $manifest -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$versionedZipPath = Join-Path $distDir "scene_qc_validator_by_mutaform_studio_v$version.zip"

if (Test-Path -LiteralPath $distDir) {
    Remove-Item -LiteralPath $distDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null

# The archive must hold one top-level "scene_qc_validator" folder, so stage the
# add-on inside a wrapper directory and zip the wrapper.
$stagingRoot = Join-Path $distDir "_stage"
$stagingAddon = Join-Path $stagingRoot "scene_qc_validator"
New-Item -ItemType Directory -Force -Path $stagingAddon | Out-Null

Copy-Item -Path (Join-Path $addonDir "*") -Destination $stagingAddon -Recurse -Force

Get-ChildItem -LiteralPath $stagingAddon -Directory -Recurse -Filter "__pycache__" |
    Remove-Item -Recurse -Force

Get-ChildItem -LiteralPath $stagingAddon -File -Recurse |
    Where-Object {
        $_.Extension -in @(".pyc", ".pyo") -or
        $_.Name -in @(".DS_Store", "Thumbs.db") -or
        $_.Name -match "\.blend\d+$"
    } |
    Remove-Item -Force

# Entries are added one by one with their names spelled out: both
# Compress-Archive and ZipFile::CreateFromDirectory write "\" separators on
# Windows PowerShell 5.1, and only Windows can unpack those. The ZIP format
# wants "/".
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::Open(
    $zipPath,
    [System.IO.Compression.ZipArchiveMode]::Create
)
try {
    $prefixLength = $stagingRoot.TrimEnd('\').Length + 1
    foreach ($file in Get-ChildItem -LiteralPath $stagingRoot -File -Recurse | Sort-Object FullName) {
        $entryName = $file.FullName.Substring($prefixLength).Replace('\', '/')
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive,
            $file.FullName,
            $entryName,
            [System.IO.Compression.CompressionLevel]::Optimal
        ) | Out-Null
    }
} finally {
    $archive.Dispose()
}
Copy-Item -LiteralPath $zipPath -Destination $versionedZipPath -Force
Remove-Item -LiteralPath $stagingRoot -Recurse -Force

Write-Host "Built $zipPath"
Write-Host "Built $versionedZipPath"
