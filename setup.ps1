param([switch]$Cuda124)
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    py -3.10 -m venv (Join-Path $ProjectRoot ".venv")
}

& $Python -m pip install --upgrade pip
if ($Cuda124) {
    & $Python -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
} else {
    & $Python -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
}
& $Python -m pip install -e $ProjectRoot
& $Python -m pip check
Write-Host "Installed. Run: & '$Python' -m image_cleanup.cli prepare-models"
