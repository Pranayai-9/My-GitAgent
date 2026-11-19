# 🤖 Autonomous Open-Source Contribution Agent

A scheduled agent running via **GitHub Actions every 4 days** that finds open-source issues, generates clean patches using the **Google Gemini API**, pushes them to your personal fork, and **emails you a one-click review link** before any PR touches public repos.

---

## 🔒 Human-in-the-Loop Safety First
Open-source maintainers hate automated "AI slop" PRs. This agent:
1. **Never submits PRs directly.** It only forks, creates a branch on your personal fork, and pushes the commit.
2. **Filters forbidden repos.** Checks `CONTRIBUTING.md` and skips repos that prohibit AI or automated PRs.
3. **Avoids claimed issues.** Detects assignees or comments like *"Can I take this?"*.
4. **Sends an approval email.** Includes a direct link to the GitHub PR comparison screen with the diff preview so you can manually review, adjust, and hit **"Create pull request"**.

---

## 📁 Repository Structure
```
├── .github/
│   └── workflows/
│       └── run-agent.yml     # Cron workflow (0 9 */4 * *)
├── finder.py                 # Issue search & anti-spam guardrails
├── solver.py                 # Gemini API code inspection & patch generator
├── notifier.py               # HTML email dispatcher via SMTP
├── main.py                   # Orchestration state machine
└── requirements.txt          # Python dependencies
```

---

## ⚙️ Setup Instructions

### 1. Create a Repository for the Agent
1. Create a new **private** repository on GitHub (e.g., `oss-contribution-agent`).
2. Push all the files from this directory to the repository.

### 2. Configure GitHub Secrets
In your GitHub repo, go to **Settings > Secrets and variables > Actions** and add the following repository secrets:

| Secret Name | Description | Example / Notes |
|---|---|---|
| `GH_PAT` | GitHub Personal Access Token (classic with `repo` scope, or fine-grained token with repo fork/push permissions) | `ghp_xxxxxxxxxxxx` |
| `GH_USERNAME` | Your GitHub username | `octocat` |
| `GEMINI_API_KEY` | Gemini API key from Google AI Studio | `AIzaSy...` |
| `NOTIFICATION_EMAIL_TO` | Email address where you want to receive PR review requests | `you@example.com` |
| `SMTP_HOST` | SMTP server for sending emails | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | `your-sender-email@gmail.com` |
| `SMTP_PASS` | SMTP App Password (e.g. Google App Password) | `xxxx xxxx xxxx xxxx` |

> **Note for Gmail users:** Generate an **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) rather than using your primary account password.

---

## ⏱️ Schedule
The workflow is configured in [.github/workflows/run-agent.yml](.github/workflows/run-agent.yml) to run every 4 days at 09:00 UTC:
```yaml
schedule:
  - cron: '0 9 */4 * *'
```
You can also trigger it on demand anytime via the **Actions** tab by selecting **OSS Contribution Agent** and clicking **Run workflow**.
