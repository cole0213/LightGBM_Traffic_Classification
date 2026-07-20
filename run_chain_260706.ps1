# run_chain_260706.ps1 — 260706 순차 ingest 체인 (Claude 세션 생성, PS 5.1)
# 미투입 날짜(07.02/03/05) 처리 후, 기존 3종을 새 파이프라인(표시명 정규화+커버리지, 0701은 v1.1 모델)으로 재생성.
# 다른 pipeline.py 프로세스가 돌고 있으면 끝날 때까지 대기 (동시 실행 = 반속).
# 로그: _chain_260706.log (이 폴더)

$ErrorActionPreference = "Continue"
$py     = "C:\Users\심규상\AppData\Local\Programs\Python\Python314\python.exe"
$pipe   = "V:\nmlab\99_sgs\lab_dashboard\pipeline.py"
$dsroot = "V:\nmlab\99_sgs\lab_dashboard\static\datasets"
$log    = "V:\nmlab\99_sgs\lab_dashboard\_chain_260706.log"
$env:PYTHONIOENCODING = "utf-8"

function Log($m) {
    Add-Content -Path $log -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" -Encoding UTF8
}

function Wait-NoOtherPipeline {
    while ($true) {
        $p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
             Where-Object { $_.CommandLine -match 'pipeline\.py' }
        if (-not $p) { return }
        Start-Sleep -Seconds 60
    }
}

# 다른 주체가 같은 키를 지금 처리 중이면 true (updated가 5분 이내인 running 잡)
function Test-FreshRunning($key) {
    $jp = Join-Path $dsroot "$key\_job.json"
    if (-not (Test-Path $jp)) { return $false }
    try { $j = Get-Content $jp -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $false }
    if ($j.state -ne "running") { return $false }
    $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    return (($now - [double]$j.updated) -lt 300)
}

$jobs = @(
    @{ src = "Z:\data\99_KJM\auto_match_out_div\2026.07.02"; key = "lab0702";      name = "연구실 수집 2026-07-02"; auto = $false },
    @{ src = "Z:\data\99_KJM\auto_match_out_div\2026.07.03"; key = "lab0703";      name = "연구실 수집 2026-07-03"; auto = $false },
    @{ src = "Z:\data\99_KJM\auto_match_out_div\2026.07.05"; key = "lab0705";      name = "연구실 수집 2026-07-05"; auto = $false },
    @{ src = "Z:\data\99_KJM\auto_match_out_div\2026.06.29"; key = "lab0629";      name = "연구실 수집 2026-06-29"; auto = $false },
    @{ src = "Z:\data\99_KJM\auto_match_out_div\2026.06.30"; key = "lab0630";      name = "연구실 수집 2026-06-30"; auto = $false },
    @{ src = "Z:\data\99_KJM\auto_match_out_div\2026.07.01"; key = "lab0701_auto"; name = "연구실 수집 2026-07-01 (ML 자동라벨)"; auto = $true }
)

Log "=== chain start (jobs: $($jobs.Count)) ==="
foreach ($j in $jobs) {
    Wait-NoOtherPipeline
    if (Test-FreshRunning $j.key) { Log "SKIP $($j.key) - 다른 프로세스가 처리 중"; continue }
    $dd = Join-Path $dsroot $j.key
    if (Test-Path (Join-Path $dd "data.json")) {
        Copy-Item (Join-Path $dd "data.json") (Join-Path $dd "data.json.bak_predisplay") -Force
        Log "backup $($j.key)/data.json -> .bak_predisplay"
    }
    $argv = @($pipe, "--src", $j.src, "--key", $j.key, "--name", $j.name)
    if ($j.auto) { $argv += "--auto-label" }
    Log "START $($j.key) <- $($j.src)"
    & $py @argv 2>&1 | ForEach-Object { Add-Content -Path $log -Value ("    " + $_.ToString()) -Encoding UTF8 }
    Log "END $($j.key) exit=$LASTEXITCODE"
}
Log "=== chain done ==="
