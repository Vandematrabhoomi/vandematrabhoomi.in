# Vande Matrabhoomi — local backup trigger for the cloud news update.
# Checks how old the live news data is; if GitHub's cron has stalled (last
# news-data.js commit older than 3.5 h), fires a workflow_dispatch so
# GitHub's cloud runners refresh the news. Dispatched runs are never dropped
# by GitHub's scheduler (only cron events are). Does NOT run Python or git
# locally — nothing to race with the GitHub Actions workflow — and the
# staleness gate means repeated invocations are harmless.
#
# Scheduled by the 'VM_News_CloudTrigger' Task Scheduler task:
#   - daily 07:00 IST (wakes the PC from sleep; catches up if missed),
#     repeating every 2 h until 22:00 while the PC is on
#   - at every logon
# Safe to run by hand any time.

$proj = "C:\Users\Arshia4\Vande Matrabhoomi News Portal"
$log  = Join-Path $proj "update_log.txt"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

try {
    # How old is the live news data? (public API, no auth)
    $c = Invoke-RestMethod -Uri 'https://api.github.com/repos/Vandematrabhoomi/vandematrabhoomi.in/commits?path=news-data.js&per_page=1' `
        -Headers @{ 'User-Agent' = 'VM-local-trigger' }
    $last = [DateTime]::Parse($c[0].commit.committer.date).ToUniversalTime()
    $ageH = [Math]::Round(((Get-Date).ToUniversalTime() - $last).TotalHours, 1)

    if ($ageH -lt 3.5) {
        Add-Content -Path $log -Value "[$stamp] VM_News_CloudTrigger: news is fresh (last update $ageH h ago) - no dispatch needed"
        exit 0
    }

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

    Add-Content -Path $log -Value "[$stamp] VM_News_CloudTrigger: news was $ageH h old - dispatched cloud update (workflow_dispatch OK)"
} catch {
    Add-Content -Path $log -Value "[$stamp] VM_News_CloudTrigger: FAILED - $($_.Exception.Message)"
    exit 1
}
