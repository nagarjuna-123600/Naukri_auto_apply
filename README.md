# Naukri Auto Apply Bot

Automatically logs into Naukri.com every 2 hours and applies to matching jobs in Hyderabad.

## How it works
- Runs on GitHub Actions every 2 hours (free, no server needed)
- Searches for Java, Python, and SQL Developer jobs
- Skips senior/lead roles, applies only to fresher-level jobs
- Saves applied jobs log to avoid duplicate applications

## Setup GitHub Secrets
Go to your repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret Name | Value |
|---|---|
| `NAUKRI_EMAIL` | Your Naukri email |
| `NAUKRI_PASSWORD` | Your Naukri password |

## Manual trigger
Go to Actions tab → Naukri Auto Apply Bot → Run workflow
# Trigger scheduled workflow - Thu Jun 25 09:54:51 UTC 2026
# trigger Fri Jun 26 07:06:45 UTC 2026
