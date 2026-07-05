# Vande Matrabhoomi — local backup trigger for the cloud news update.
# Fires a workflow_dispatch for .github/workflows/update-news.yml so GitHub's
# cloud runners refresh the news. Manually dispatched runs are never dropped
# by GitHub's scheduler (only cron events are), so this guarantees at least
# one update on any day this PC is powered on, even if every cron event was
# skipped. It does NOT run Python or git locally — nothing to race with the
# GitHub Actions workflow.
#
# Scheduled by the 'VM_News_CloudTrigger' Task Scheduler task (daily 09:00,
# runs late if the PC was off at 09:00). Safe to run by hand any time.

$proj = "C:\Users\Arshia4\Vande Matrabhoomi News Portal"
$log  = Join-Path $proj "update_log.txt"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

try {
    # Token lives only in the git remote URL; read it fresh each run so a
    # rotated token propagates automatically.
    $remote = git -C $proj remote get-url origin 2>$null
    if ($remote -notmatch 'https://[^:]*:?([A-Za-z0-9_]+)@github\.com') {
        throw "could not extract token from git remote URL"
    }
    $token = $Matches[1]

    Invoke-RestMethod -Method Post `
        -Uri 'https://api.github.com/repos/Vandematrabhoomi/vandematrabhoomi.in/actions/workflows/update-news.yml/dispatches' `
        -Headers @{ Authorization = "token $token"; 'User-Agent' = 'VM-local-trigger' } `
        -Body '{"ref":"main"}' -ContentType 'application/json' | Out-Null

    Add-Content -Path $log -Value "[$stamp] VM_News_CloudTrigger: dispatched cloud news update (workflow_dispatch OK)"
} catch {
    Add-Content -Path $log -Value "[$stamp] VM_News_CloudTrigger: FAILED - $($_.Exception.Message)"
    exit 1
}
