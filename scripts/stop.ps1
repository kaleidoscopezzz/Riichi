[CmdletBinding()]
param()
$mutex = $null
try {
  . (Join-Path $PSScriptRoot 'common.ps1')
  $mutex = Enter-LauncherLock
  $state = Read-State
  if ($null -eq $state) { Write-Host 'Riichi 启动器当前没有运行中的服务。'; exit 0 }
  if (Stop-Owned $state) { $message = 'Riichi 本次启动的前后端及子进程已停止，进程状态已清理。日志保留在 .runtime/launcher。' }
  else { $message = 'Riichi 启动进程已不存在（已退出或 PID 已被其他程序复用，未终止任何进程），已清理过期状态。日志保留在 .runtime/launcher。' }
  Remove-Item -LiteralPath $script:StateFile
  Write-Host $message
} catch {
  Write-Host "停止失败：$($_.Exception.Message)" -ForegroundColor Red
  exit 1
} finally { if ($null -ne $mutex) { $mutex.ReleaseMutex(); $mutex.Dispose() } }
