[CmdletBinding()]
param([switch]$NoBrowser, [switch]$NonInteractive)
$mutex = $null
$started = $null
try {
  . (Join-Path $PSScriptRoot 'common.ps1')
  $mutex = Enter-LauncherLock
  $state = Read-State
  if ($null -ne $state) {
    if (Test-Owner $state) {
      if ($state.status -eq 'ready' -and (Test-Http 'http://127.0.0.1:8000/api/v1/health/' -Health) -and (Test-Http 'http://127.0.0.1:5173')) {
        Write-Host 'Riichi 已启动，复用当前服务：http://127.0.0.1:5173'
        if (-not $NoBrowser) { Open-RiichiBrowser }
        exit 0
      }
      throw '已有本项目进程但服务尚未就绪或已异常；请先运行 stop.bat 核对并停止，不会重复启动。'
    }
    Remove-Item -LiteralPath $script:StateFile
    Write-Host '旧进程已退出，已清理本项目过期状态。'
  }
  Test-PortFree 8000
  Test-PortFree 5173
  function Confirm-Preparation([string]$Message, [string]$Word) {
    if ($NonInteractive) { throw "$Message 非交互模式不自动批准，请交互运行 start.bat。" }
    Write-Host $Message
    if ((Read-Host "确认请输入 $Word，其他输入取消") -cne $Word) { throw '用户取消，未继续执行。' }
  }
  function Get-Tool([string]$Override, [string]$Name) {
    if ($Override) {
      if (-not (Test-Path -LiteralPath $Override -PathType Leaf)) { throw "指定的 $Name 不存在，请检查工具配置。" }
      return [IO.Path]::GetFullPath($Override)
    }
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $command) { throw "未找到 $Name，请安装项目要求的工具并重新打开启动器。" }
    return $command.Source
  }
  $versionText = (Get-Content -LiteralPath (Join-Path $script:Root 'backend\.python-version') -Raw).Trim()
  $minimumPython = [version]$versionText
  $python = Join-Path $script:Root 'backend\.venv\Scripts\python.exe'
  $bootstrap = $null
  if (Test-Path -LiteralPath $python) { $bootstrap = $python }
  elseif ($env:RIICHI_PYTHON) { $bootstrap = Get-Tool $env:RIICHI_PYTHON 'python.exe' }
  else { $bootstrap = Find-Python $minimumPython }
  if (-not $bootstrap) { throw "未找到 Python 3.13（最低 $versionText）。请安装后重试；不会全局安装运行时。" }
  $reported = & $bootstrap '-c' 'import sys; print(chr(46).join(map(str,sys.version_info[:3])))'
  if ($LASTEXITCODE -ne 0 -or $reported -notmatch '^3\.13\.\d+$' -or [version]$reported -lt $minimumPython) { throw "Python 版本不符合要求：需要 3.13，最低 $versionText；已有虚拟环境不会被覆盖。" }
  $node = Get-Tool $env:RIICHI_NODE 'node.exe'
  $env:PATH = (Split-Path -Parent $node) + ';' + $env:PATH
  $npm = Get-Tool $env:RIICHI_NPM 'npm.cmd'
  $package = Get-Content -LiteralPath (Join-Path $script:Root 'frontend\package.json') -Raw | ConvertFrom-Json
  foreach ($tool in @(@($node, 'node'), @($npm, 'npm'))) {
    $requirement = [string]$package.engines.($tool[1])
    if ($requirement -notmatch '^>=(\d+(?:\.\d+){0,2})$') { throw 'package.json engines 已变化，请核对启动器支持的版本规则。' }
    $minimum = $Matches[1]; if (-not $minimum.Contains('.')) { $minimum += '.0' }
    $actual = ([string](Invoke-Probe $tool[0] @('--version'))).TrimStart('v') -as [version]
    if ($null -eq $actual -or $actual -lt [version]$minimum) { throw "$($tool[1]) 版本不符合 package.json 要求 $requirement。" }
  }
  Write-Host "环境检查通过：Python $reported；Node / npm 符合 package.json。"
  $probe = Join-Path $script:Root 'scripts\launcher_probe.py'
  $needsVenv = -not (Test-Path -LiteralPath $python)
  $needsPython = $true
  if (-not $needsVenv) {
    $dependencyResult = & $python $probe 'dependencies'
    $needsPython = $LASTEXITCODE -ne 0
  }
  Push-Location (Join-Path $script:Root 'frontend')
  try {
    $frontendCheck = (& $node (Join-Path $PSScriptRoot 'check_frontend.cjs')) | ConvertFrom-Json
    if ($frontendCheck.declarationMismatch) { throw 'package.json 与锁文件不一致，请先核对依赖声明。' }
    $needsNode = -not $frontendCheck.ok
    if (-not $needsNode) {
      $previousPreference = $ErrorActionPreference
      try { $ErrorActionPreference = 'Continue'; & $npm 'ls' '--all' '--json' 2>$null | Out-Null; $needsNode = $LASTEXITCODE -ne 0 } finally { $ErrorActionPreference = $previousPreference }
      $lockHash = (Get-FileFingerprint (Join-Path $script:Root 'frontend\package-lock.json'))
      $stamp = Join-Path $script:Runtime 'frontend-lock.txt'
      if ((Test-Path -LiteralPath $stamp) -and (Get-Content -LiteralPath $stamp -Raw).Trim() -ne $lockHash) { $needsNode = $true }
    }
  } finally { Pop-Location }
  if ($needsVenv -or $needsPython -or $needsNode) {
    Confirm-Preparation '首次使用或依赖已变化：将在项目内准备虚拟环境与锁定依赖，可能需要联网。不会改数据库。' 'PREPARE'
    if ($needsVenv) { & $bootstrap '-m' 'venv' (Join-Path $script:Root 'backend\.venv'); if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败。' } }
    if ($needsPython) { & $python '-m' 'pip' 'install' '-r' (Join-Path $script:Root 'backend\requirements.txt'); if ($LASTEXITCODE -ne 0) { throw 'Python 依赖安装失败，请检查网络及 requirements.txt。' } }
    if ($needsNode) {
      Push-Location (Join-Path $script:Root 'frontend')
      try { & $npm 'ci'; if ($LASTEXITCODE -ne 0) { throw 'npm ci 失败，请检查网络、Node版本或锁文件。' } } finally { Pop-Location }
    }
  } else { Write-Host '现有依赖满足锁定版本，跳过安装。' }
  (Get-FileFingerprint (Join-Path $script:Root 'frontend\package-lock.json')) | Set-Content -LiteralPath (Join-Path $script:Runtime 'frontend-lock.txt') -Encoding Ascii
  if (-not (Test-Path -LiteralPath (Join-Path $script:Root 'backend\.env')) -and -not $env:SECRET_KEY) {
    Confirm-Preparation '没有本地配置。将从 .env.example 创建仅本地使用的 .env，并生成随机密钥（不显示、不覆盖已有文件）。' 'CONFIGURE'
    & $python $probe 'configure' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '本地配置创建失败，未覆盖已有文件。' }
  }
  function Read-Probe {
    $json = & $python $probe 'check'
    $result = $json | ConvertFrom-Json
    if (-not $result.ok) { throw "配置/数据库检查失败（$($result.error)）：$($result.message)" }
    return $result
  }
  $database = Read-Probe
  Write-Host "目标数据库：$($database.database)"
  if (@($database.pending).Count -gt 0) {
    Write-Host ('待执行迁移：' + ($database.pending -join ', '))
    Confirm-Preparation '请先确认目标数据库及备份。只有明确同意才执行已有迁移；不会清库、重建或伪造状态。' 'MIGRATE'
    Push-Location (Join-Path $script:Root 'backend')
    try { & $python 'manage.py' 'migrate' '--noinput'; if ($LASTEXITCODE -ne 0) { throw '数据库迁移失败，停止启动；请保留现场核对，不要重置数据库。' } } finally { Pop-Location }
    $database = Read-Probe
    if (@($database.pending).Count -gt 0) { throw '迁移后仍存在待执行项，停止启动。' }
  }
  if (-not $database.admin) { Write-Host '尚无有效管理员。请另开终端进入 backend，交互运行：.\.venv\Scripts\python.exe manage.py init_admin（没有默认密码）。' -ForegroundColor Yellow }
  $runId = [guid]::NewGuid().ToString('N')
  $runFolder = Join-Path $script:Runtime $runId
  [IO.Directory]::CreateDirectory($runFolder) | Out-Null
  @{ python=$python; node=$node } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runFolder 'launch.json') -Encoding UTF8
  $workerPath = Join-Path $PSScriptRoot 'run.ps1'
  $arguments = @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File',$workerPath,'-RunId',$runId)
  $owner = [RiichiLauncher.ProcessJob]::LaunchOwner((Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'), $arguments, $script:Root)
  $started = [pscustomobject]@{ root=$script:Root; runId=$runId; owner=$owner; status='starting'; backend=$null; frontend=$null; error=$null }
  Write-State $started
  $lastStatus = ''
  $deadline = [DateTime]::UtcNow.AddSeconds(100)
  do {
    $state = Read-State -Required
    if ($state.status -ne $lastStatus) { Write-Host "进程状态：$($state.status)"; $lastStatus = $state.status }
    if ($state.status -eq 'failed') { throw "服务启动失败：$($state.error)；日志保存在 .runtime/launcher/$runId。" }
    if ($state.status -eq 'ready') { break }
    if (-not (Test-Owner $state)) { throw "启动进程已退出。请检查 .runtime/launcher/$runId 日志。" }
    Start-Sleep -Milliseconds 250
  } while ([DateTime]::UtcNow -lt $deadline)
  if ($state.status -ne 'ready') { throw '服务就绪超时，停止本次创建的进程。' }
  Write-Host "后端 PID $($state.backend.ProcessId)：http://127.0.0.1:8000/api/v1/health/"
  Write-Host "前端 PID $($state.frontend.ProcessId)：http://127.0.0.1:5173"
  Write-Host 'Riichi 已就绪。关闭本窗口不停止服务；退出时双击 stop.bat。'
  $started = $null # The hidden owner now holds the job until stop.bat.
  if (-not $NoBrowser) { Open-RiichiBrowser }
} catch {
  Write-Host "启动失败：$($_.Exception.Message)" -ForegroundColor Red
  if ($null -ne $started) {
    try { $null = Stop-Owned $started; if (Test-Path -LiteralPath $script:StateFile) { Remove-Item -LiteralPath $script:StateFile } } catch { Write-Host '自动回收无法完成；已拒绝终止身份不符的进程，请核对状态。' }
  }
  exit 1
} finally { if ($null -ne $mutex) { $mutex.ReleaseMutex(); $mutex.Dispose() } }
