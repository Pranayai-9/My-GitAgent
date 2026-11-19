import os
import subprocess
import tempfile
import sys
from github import Github
from finder import find_target_issue
from solver import plan_and_patch, apply_patch
from notifier import send_review_email

def run_command(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout + ("\n" + res.stderr if res.stderr else "")

def main():
    token = os.environ.get("GITHUB_TOKEN")
    gh_user = os.environ.get("GH_USERNAME")
    search_language = os.environ.get("SEARCH_LANGUAGE", "python")

    if not token or not gh_user:
        print("ERROR: GITHUB_TOKEN and GH_USERNAME environment variables are required.")
        sys.exit(1)

    gh = Github(token)
    user = gh.get_user()

    print(f"Logged in as GitHub User: {user.login}")

    # 1. Discover suitable issue
    repo, issue = find_target_issue(gh, language=search_language)
    if not repo or not issue:
        print("No issue to work on today. Exiting cleanly.")
        return

    print(f"Target repository: {repo.full_name}")
    print(f"Target issue #{issue.number}: {issue.title}")

    # 2. Fork repository to authenticated user
    print(f"Ensuring fork exists under {user.login}...")
    user_fork = user.create_fork(repo)
    print(f"Fork ready: {user_fork.html_url}")

    # 3. Clone fork locally into temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        clone_url = f"https://x-access-token:{token}@github.com/{user.login}/{repo.name}.git"
        branch_name = f"fix-issue-{issue.number}"

        print(f"Cloning {user.login}/{repo.name}...")
        code, out = run_command(["git", "clone", clone_url, temp_dir])
        if code != 0:
            print(f"Git clone failed: {out}")
            return

        # Ensure upstream is tracked and fetch upstream branch
        run_command(["git", "remote", "add", "upstream", f"https://github.com/{repo.full_name}.git"], cwd=temp_dir)
        run_command(["git", "fetch", "upstream"], cwd=temp_dir)

        # Checkout new branch
        run_command(["git", "checkout", "-b", branch_name], cwd=temp_dir)

        # 4. Generate patch using Gemini API
        patch_result = plan_and_patch(
            repo_path=temp_dir,
            issue_title=issue.title,
            issue_body=issue.body or ""
        )

        modified = apply_patch(temp_dir, patch_result)
        if not modified:
            print("No files modified by solver. Aborting.")
            return

        # 5. Optional Sandbox Test Execution (e.g. pytest)
        print("Running tests if pytest is present...")
        test_code, test_out = run_command(["pytest", "-q"], cwd=temp_dir)
        print(f"Pytest result (exit {test_code}):\n{test_out[:500]}")

        # 6. Commit and Push to Fork
        run_command(["git", "add", "."], cwd=temp_dir)
        commit_msg = f"fix: address issue #{issue.number} - {issue.title[:50]}\n\nAutomated draft fix by Gemini for review."
        run_command(["git", "commit", "-m", commit_msg], cwd=temp_dir)
        
        print(f"Pushing branch {branch_name} to fork...")
        push_code, push_out = run_command(["git", "push", "-u", "origin", branch_name, "--force"], cwd=temp_dir)
        if push_code != 0:
            print(f"Git push failed: {push_out}")
            return

        # 7. Collect Diff & Summary
        _, diff_out = run_command(["git", "diff", "HEAD~1", "HEAD"], cwd=temp_dir)
        diff_snippet = diff_out[:3500] + ("\n... [truncated]" if len(diff_out) > 3500 else "")

        fork_branch_url = f"https://github.com/{user.login}/{repo.name}/tree/{branch_name}"
        compare_pr_url = f"https://github.com/{repo.full_name}/compare/main...{user.login}:{repo.name}:{branch_name}?expand=1"

        # 8. Notify via Email for Human Approval
        print("Dispatching review notification email...")
        send_review_email(
            issue_title=issue.title,
            issue_url=issue.html_url,
            repo_full_name=repo.full_name,
            fork_branch_url=fork_branch_url,
            diff_summary=diff_snippet or patch_result.get("explanation", "Patch applied."),
            compare_pr_url=compare_pr_url
        )

        print("\n✅ Run completed successfully. Check your email to review and open the PR!")

if __name__ == "__main__":
    main()
