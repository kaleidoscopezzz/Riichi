param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$RunId)
$job = $null
$state = $null
$runFolder = Join-Path ([IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))) ".runtime\launcher\$RunId"
try {
  . (Join-Path $PSScriptRoot 'common.ps1')
  $runFolder = Join-Path $script:Runtime $RunId
  $launch = Get-Content -LiteralPath (Join-Path $runFolder 'launch.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  $deadline = [DateTime]::UtcNow.AddSeconds(10)
  do {
    $state = Read-State
    if ($null -ne $state -and $state.runId -eq $RunId) { break }
    Start-Sleep -Milliseconds 100
  } while ([DateTime]::UtcNow -lt $deadline)
  if ($null -eq $state -or $state.runId -ne $RunId -or $state.owner.ProcessId -ne $PID) { throw '启动状态身份不匹配。' }
  $job = New-Object RiichiLauncher.ProcessJob
  $env:API_PROXY_TARGET = 'http://127.0.0.1:8000'
  $env:VITE_API_BASE_URL = 'http://127.0.0.1:5173'
  $state.status = 'backend'
  $state.backend = $job.Spawn($launch.python, @((Join-Path $script:Root 'backend\manage.py'),'runserver','127.0.0.1:8000','--noreload'), (Join-Path $script:Root 'backend'), (Join-Path $runFolder 'backend.log'))
  Write-State $state
  function Wait-Service($Identity, [int]$Port, [string]$Url, [switch]$Health) {
    $until = [DateTime]::UtcNow.AddSeconds(40)
    do {
      if ($null -eq [RiichiLauncher.ProcessJob]::Snapshot([int]$Identity.ProcessId)) { throw "端口 $Port 对应服务已退出，请检查本轮日志。" }
      if (Test-Http $Url -Health:$Health) {
        $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if ($listeners.Count -gt 0 -and @($listeners | Where-Object { -not $job.Contains([int]$_.OwningProcess) }).Count -eq 0) { return }
        throw "端口 $Port 归属不符，拒绝使用其他进程的服务。"
      }
      Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $until)
    throw "端口 $Port 服务就绪超时，请检查日志。"
  }
  Wait-Service $state.backend 8000 'http://127.0.0.1:8000/api/v1/health/' -Health
  $state.status = 'frontend'
  $state.frontend = $job.Spawn($launch.node, @((Join-Path $script:Root 'frontend\node_modules\vite\bin\vite.js'),'--host','127.0.0.1','--port','5173','--strictPort'), (Join-Path $script:Root 'frontend'), (Join-Path $runFolder 'frontend.log'))
  Write-State $state
  Wait-Service $state.frontend 5173 'http://127.0.0.1:5173'
  $state.status = 'ready'
  Write-State $state
  while ($null -ne [RiichiLauncher.ProcessJob]::Snapshot([int]$state.backend.ProcessId) -and $null -ne [RiichiLauncher.ProcessJob]::Snapshot([int]$state.frontend.ProcessId)) { Start-Sleep -Seconds 1 }
  throw '前端或后端进程已退出，正在回收本次启动的其他进程。'
} catch {
  [IO.File]::WriteAllText((Join-Path $runFolder 'worker-error.log'), $_.Exception.Message, (New-Object Text.UTF8Encoding($false)))
  if ($null -ne $state) { $state.status='failed'; $state.error=$_.Exception.Message; Write-State $state }
  exit 1
} finally { if ($null -ne $job) { $job.Dispose() } }
