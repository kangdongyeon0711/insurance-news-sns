<#
.SYNOPSIS
    register_scheduler_task.ps1로 등록한 작업 스케줄러 작업을 제거한다.

.사용법
    powershell -ExecutionPolicy Bypass -File scripts\windows\unregister_scheduler_task.ps1
#>

param(
    [string]$TaskName = "InsuranceNewsScheduler"
)

$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $Task) {
    Write-Host "'$TaskName' 작업이 등록되어 있지 않습니다. 할 일이 없습니다."
    exit 0
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false

Write-Host "작업 스케줄러에서 '$TaskName' 작업을 제거했습니다."
