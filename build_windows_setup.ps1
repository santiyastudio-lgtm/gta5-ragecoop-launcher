$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$isccCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    "C:\Program Files\Inno Setup 5\ISCC.exe"
)

$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup compiler ISCC.exe not found. Install Inno Setup 6 first."
}

$iss = Join-Path $projectRoot "installer\GTA5CoopSetup.iss"
& $iscc $iss

$setup = Join-Path $projectRoot "dist\GTA5CoopSetup.exe"
if (-not (Test-Path -LiteralPath $setup)) {
    throw "Setup was not created: $setup"
}

Get-Item -LiteralPath $setup | Select-Object FullName, Length, LastWriteTime
