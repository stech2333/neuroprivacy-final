param(
    [Parameter(Mandatory)][ValidateSet('stieger','openbmi')][string]$Dataset,
    [Parameter(Mandatory)][int]$WaveformWorker,
    [int]$EarlierGpuWorker = 0
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runtime = 'E:\Python\envs\deep-gpu\python.exe'
Set-Location -LiteralPath $root
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:OPENBLAS_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'

function Wait-ForWorker([int]$ProcessId) {
    if ($ProcessId -eq 0) { return }
    $instance = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($instance) { Wait-Process -InputObject $instance }
}
Wait-ForWorker $WaveformWorker
$receipt = Join-Path $root "results\raw_reproduction\$Dataset\complete.json"
if (-not (Test-Path -LiteralPath $receipt)) { throw "Missing waveform reproduction receipt for $Dataset." }
if ($Dataset -eq 'stieger') {
    $env:CUDA_VISIBLE_DEVICES = '-1'
    & $runtime -X utf8 -s -u -m neuroprivacy.raw_eval stieger
} else {
    Wait-ForWorker $EarlierGpuWorker
    & $runtime -X utf8 -s -u -m neuroprivacy.gpu_reproduction openbmi
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
