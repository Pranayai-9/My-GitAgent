import re
from github import Github
from github.Issue import Issue
from github.Repository import Repository

def find_target_issue(gh: Github, language: str = "python") -> tuple[Repository, Issue] | tuple[None, None]:
    """
    Search for open, unassigned 'good first issue' or 'help wanted' issues in the given language.
    Applies safety guardrails to avoid toxic PRs or AI-forbidden repositories.
    """
    query = f"is:issue is:open label:\"good first issue\",\"help wanted\" language:{language} no:assignee comments:<5"
    print(f"[Finder] Searching GitHub issues with query: {query}")

    issues = gh.search_issues(query=query, sort="created", order="desc")

    for issue in issues[:30]:
        try:
            repo = issue.repository
            print(f"[Finder] Checking issue #{issue.number} on {repo.full_name}: {issue.title}")

            # 1. Skip archived, disabled, or locked repos
            if repo.archived or repo.disabled or issue.locked:
                print("   Skipped: Repo is archived, disabled, or issue is locked.")
                continue

            # 2. Check if repo explicitly bans automated / AI PRs in CONTRIBUTING.md or README.md
            if is_ai_disallowed(repo):
                print("   Skipped: Repo guidelines disallow AI/automated contributions.")
                continue

            # 3. Check issue comments for people already claiming work
            if has_claim_comments(issue):
                print("   Skipped: Someone in comments already claimed the issue.")
                continue

            # Found an ideal issue
            print(f"[Finder] Selected Issue: {issue.html_url}")
            return repo, issue

        except Exception as e:
            print(f"[Finder] Error inspecting issue: {e}")
            continue

    print("[Finder] No suitable issue found.")
    return None, None

def is_ai_disallowed(repo: Repository) -> bool:
    disallowed_keywords = [
        "no ai", "no automated pr", "no llm", "disallow ai", "prohibit ai", 
        "ban ai", "ai-generated pull request"
    ]
    files_to_check = ["CONTRIBUTING.md", "README.md", ".github/CONTRIBUTING.md"]

    for file_path in files_to_check:
        try:
            content_file = repo.get_contents(file_path)
            decoded_text = content_file.decoded_content.decode("utf-8", errors="ignore").lower()
            for kw in disallowed_keywords:
                if kw in decoded_text:
                    return True
        except Exception:
            continue

    return False

def has_claim_comments(issue: Issue) -> bool:
    claim_patterns = [
        r"i('d| would| will)? like to work on this",
        r"can i take this",
        r"assign (it to )?me",
        r"working on (this|it)",
        r"taking this up"
    ]
    for comment in issue.get_comments():
        body = comment.body.lower()
        for pattern in claim_patterns:
            if re.search(pattern, body):
                return True
    return False
