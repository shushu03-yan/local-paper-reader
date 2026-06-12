param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$resolvedPython = $null

if (Test-Path $Python) {
    $resolvedPython = (Resolve-Path $Python).Path
} else {
    $command = Get-Command $Python -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        $resolvedPython = $command.Source
    }
}

if (-not $resolvedPython) {
    throw "Python executable not found. Pass -Python with an absolute path or activate the correct environment first."
}

Write-Host "Using Python: $resolvedPython"
& $resolvedPython -c "import sys; print(sys.version)"
& $resolvedPython -c "import paddle; print('paddle', paddle.__version__); print('cuda', paddle.device.is_compiled_with_cuda())"
& $resolvedPython -m pip show fastapi paddleocr paddlepaddle-gpu paddlex | Out-Host
& $resolvedPython .\scripts\process_pdf_cli.py --self-check
& $resolvedPython .\scripts\run_server.py --host $HostName --port $Port
