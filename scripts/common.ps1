Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') { throw '此启动器仅支持 Windows。其他系统请使用手动启动文档。' }
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { } # Hidden owner has no console.
$script:Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$script:Runtime = Join-Path $script:Root '.runtime\launcher'
$script:StateFile = Join-Path $script:Runtime 'state.json'
foreach ($relative in @('.runtime', '.runtime\launcher', '.cache', '.cache\launcher')) {
  $folder = Join-Path $script:Root $relative
  if ((Test-Path -LiteralPath $folder) -and ((Get-Item -LiteralPath $folder).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw '运行/缓存目录不能是链接，请人工核对。' }
  [IO.Directory]::CreateDirectory($folder) | Out-Null
}
[IO.Directory]::CreateDirectory($script:Runtime) | Out-Null
$env:TEMP = Join-Path $script:Root '.cache\launcher'
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $script:Root '.cache\pip'
$env:npm_config_cache = Join-Path $script:Root '.cache\npm'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
if (-not ('RiichiLauncher.ProcessJob' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'LauncherProcess.cs') }

function Enter-LauncherLock {
  $hash = [Security.Cryptography.SHA256]::Create()
  try { $key = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($script:Root.ToLowerInvariant()))).Replace('-', '') } finally { $hash.Dispose() }
  $mutex = New-Object Threading.Mutex($false, "Local\Riichi-$key")
  try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
  if (-not $locked) { $mutex.Dispose(); throw '已有启动或停止操作进行中，请稍后重试；不会创建重复服务。' }
  return $mutex
}
function Get-FileFingerprint([string]$Path) {
  $stream = [IO.File]::OpenRead($Path)
  $algorithm = [Security.Cryptography.SHA256]::Create()
  try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '') }
  finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Write-State($State) {
  $temporary = Join-Path $script:Runtime ("state-$([guid]::NewGuid().ToString('N')).tmp")
  [IO.File]::WriteAllText($temporary, ($State | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
  if (Test-Path -LiteralPath $script:StateFile) { [IO.File]::Replace($temporary, $script:StateFile, [NullString]::Value) }
  else { [IO.File]::Move($temporary, $script:StateFile) }
}
function Test-StateShape($State) {
  # Under StrictMode a missing field would throw later; reject it as damage.
  if ($State -isnot [Management.Automation.PSCustomObject]) { return $false }
  foreach ($name in @('root', 'runId', 'owner', 'status', 'backend', 'frontend', 'error')) { if ($null -eq $State.PSObject.Properties[$name]) { return $false } }
  if ($null -eq $State.owner) { return $false }
  foreach ($identity in @($State.owner, $State.backend, $State.frontend)) {
    if ($null -eq $identity) { continue }
    if ($identity -isnot [Management.Automation.PSCustomObject]) { return $false }
    foreach ($name in @('ProcessId', 'CreationTime', 'ImagePath')) { if ($null -eq $identity.PSObject.Properties[$name]) { return $false } }
    if ([string]$identity.ProcessId -notmatch '^\d+$' -or [string]$identity.CreationTime -notmatch '^\d+$') { return $false }
  }
  return ($State.status -is [string])
}
function Read-State([switch]$Required) {
  # File.Replace is not atomic for readers: a poll can briefly hit a missing,
  # empty or half-swapped file. Retry those; still unreadable means damage.
  for ($attempt = 1; ; $attempt++) {
    try {
      if (-not (Test-Path -LiteralPath $script:StateFile)) {
        if (-not $Required) { return $null }
        throw (New-Object IO.FileNotFoundException)
      }
      # Readers allow atomic replacement; Get-Content's sharing mode can otherwise
      # race the worker's phase updates on Windows PowerShell 5.1.
      $stream = [IO.File]::Open($script:StateFile, [IO.FileMode]::Open, [IO.FileAccess]::Read, ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
      $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8, $true)
      try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
      if ([string]::IsNullOrWhiteSpace($text)) { throw (New-Object IO.InvalidDataException) }
      $state = $text | ConvertFrom-Json
      if (-not (Test-StateShape $state)) { throw (New-Object IO.InvalidDataException) }
      break
    } catch {
      if ($attempt -ge 20) { throw '启动状态文件缺失、为空或格式损坏，已拒绝管理进程，请人工核对 .runtime/launcher。' }
      Start-Sleep -Milliseconds 50
    }
  }
  if ($state.root -ne $script:Root -or $state.runId -notmatch '^[a-f0-9]{32}$') { throw '启动状态不属于当前目录或格式损坏，已拒绝管理进程，请人工核对 .runtime/launcher。' }
  return $state
}
function Test-Alive($Identity) {
  # Same PID and creation time. A later process reusing the PID is not ours.
  $current = [RiichiLauncher.ProcessJob]::Snapshot([int]$Identity.ProcessId)
  return ($null -ne $current -and $current.CreationTime -eq [string]$Identity.CreationTime)
}
function Assert-ChildrenGone($State) {
  # KILL_ON_JOB_CLOSE reclaims the tree once the owner exits, asynchronously;
  # wait briefly. A child still alive with its recorded identity is never
  # terminated here: that is an anomaly for manual review.
  $deadline = [DateTime]::UtcNow.AddSeconds(5)
  foreach ($child in @($State.backend, $State.frontend)) {
    if ($null -eq $child) { continue }
    while (Test-Alive $child) {
      if ([DateTime]::UtcNow -ge $deadline) { throw "启动进程已退出，但子进程 PID $($child.ProcessId) 仍以原身份运行；未终止任何进程，请人工核对。" }
      Start-Sleep -Milliseconds 100
    }
  }
}
function Test-Owner($State) {
  # $false only when the owner is proven gone: no such PID, exited, or the PID
  # now belongs to a process created at another time (reuse; never touched).
  $identity = [RiichiLauncher.ProcessJob]::Snapshot([int]$State.owner.ProcessId)
  if ($null -eq $identity -or $identity.CreationTime -ne $State.owner.CreationTime) { Assert-ChildrenGone $State; return $false }
  if ($identity.ImagePath -ne $State.owner.ImagePath) { throw '进程创建时间相同但可执行路径不符或无法读取，拒绝终止；请人工核对状态文件。' }
  $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($identity.ProcessId)"
  if ($null -eq $process -or [string]::IsNullOrEmpty($process.CommandLine)) {
    # A normal exit can occur between the kernel snapshot and CIM query. Only
    # accept that case after another kernel check, never on missing CIM alone.
    if (-not (Test-Alive $State.owner)) { Assert-ChildrenGone $State; return $false }
    throw '无法确认进程命令行，拒绝终止；请人工核对状态。'
  }
  $worker = Join-Path $script:Root 'scripts\run.ps1'
  if ($process.CommandLine.IndexOf($worker, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or $process.CommandLine.IndexOf($State.runId, [StringComparison]::Ordinal) -lt 0) { throw '进程命令行不属于本次 Riichi 启动，拒绝终止。' }
  return $true
}
function Stop-Owned($State) {
  # $true when the verified owner was stopped; $false when it was already gone.
  if (-not (Test-Owner $State)) { return $false }
  [RiichiLauncher.ProcessJob]::StopVerified([int]$State.owner.ProcessId, $State.owner.CreationTime, $State.owner.ImagePath)
  return $true
}
function Test-PortFree([int]$Port) {
  $message = "端口 $Port 已被占用，未终止占用者。请先核对服务或端口。"
  # Windows lets 127.0.0.1 bind while another program listens on 0.0.0.0, ::
  # or ::1, so also connect to both loopbacks. A listener accepts within
  # milliseconds; a refused loopback connect takes about 2 s, hence the timeout.
  $probes = @()
  foreach ($address in @([Net.IPAddress]::Loopback, [Net.IPAddress]::IPv6Loopback)) {
    $client = $null
    try { $client = New-Object Net.Sockets.TcpClient($address.AddressFamily); $probes += [pscustomobject]@{ Client = $client; Pending = $client.BeginConnect($address, $Port, $null, $null) } }
    catch { if ($null -ne $client) { $client.Close() } } # e.g. IPv6 disabled; the bind test still applies.
  }
  try {
    $deadline = [DateTime]::UtcNow.AddMilliseconds(300)
    foreach ($probe in $probes) {
      $connected = $false
      if ($probe.Pending.AsyncWaitHandle.WaitOne([int][Math]::Max(0, ($deadline - [DateTime]::UtcNow).TotalMilliseconds))) {
        try { $probe.Client.EndConnect($probe.Pending); $connected = $true } catch { }
      }
      if ($connected) { throw $message }
    }
  } finally { foreach ($probe in $probes) { $probe.Client.Close() } }
  $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $Port)
  try { $listener.Start() } catch { throw $message } finally { $listener.Stop() }
}
function Invoke-Probe([string]$FilePath, [string[]]$Arguments) {
  # Windows PowerShell 5.1 turns redirected native stderr into a terminating
  # NativeCommandError under EAP=Stop. Isolate each probe: stdout or $null.
  $ErrorActionPreference = 'Continue'
  try { $output = @(& $FilePath @Arguments 2>$null) } catch { return $null }
  if ($LASTEXITCODE -ne 0) { return $null }
  return ($output -join "`n").Trim()
}
function Find-Python([version]$Minimum) {
  # Project runtime, Python Launcher, then PATH. A missing 3.13 or a failing
  # candidate never stops the search; $null when none qualifies.
  $candidates = @()
  $local = Join-Path $script:Root '.tools\python'
  if (Test-Path -LiteralPath $local) { $candidates += @(Get-ChildItem -LiteralPath $local -Directory | ForEach-Object { Join-Path $_.FullName 'python.exe' } | Where-Object { Test-Path -LiteralPath $_ }) }
  $pyCommand = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($pyCommand) {
    $found = Invoke-Probe $pyCommand.Source @('-3.13', '-c', 'import sys; print(sys.executable)')
    if ($found) { $candidates += $found }
  }
  $pathPython = Get-Command python.exe -CommandType Application -ErrorAction SilentlyContinue
  if ($pathPython) { $candidates += $pathPython.Source }
  foreach ($candidate in $candidates) {
    $reported = Invoke-Probe $candidate @('-c', 'import sys; print(chr(46).join(map(str,sys.version_info[:3])))')
    if ($reported -match '^3\.13\.\d+$' -and [version]$reported -ge $Minimum) { return $candidate }
  }
  return $null
}
function Test-Http([string]$Url, [switch]$Health) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -ne 200) { return $false }
    if ($Health) { $body = $response.Content | ConvertFrom-Json; return ($body.status -eq 'ok' -and $body.service -eq 'riichi-api') }
    return $response.Content.Contains('<div id="root">')
  } catch { return $false }
}
function Open-RiichiBrowser {
  try { Start-Process 'http://127.0.0.1:5173' -WindowStyle Normal }
  catch { Write-Host '服务已就绪，但无法调用默认浏览器。请手动打开 http://127.0.0.1:5173。' -ForegroundColor Yellow }
}
