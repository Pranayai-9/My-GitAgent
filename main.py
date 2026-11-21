import os
import subprocess
import tempfile
import sys
import traceback
from github import Github
from finder import find_target_issue
from solver import plan_and_patch, apply_patch
from notifier import send_review_email

def run_command(cmd: list[str], cwd: str | None = None) -> tuple[int, str]:
    res = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.returncode, res.stdout + ("\n" + res.stderr if res.stderr else "")

def main():
    try:
        token = os.environ.get("GITHUB_TOKEN")
        gh_user = os.environ.get("GH_USERNAME")
        search_language = os.environ.get("SEARCH_LANGUAGE", "python")

        print("=== Step 0: Checking Environment Variables ===")
        print(f"GH_USERNAME: {'[SET]' if gh_user else '[MISSING]'}")
        print(f"GITHUB_TOKEN: {'[SET - length ' + str(len(token)) + ']' if token else '[MISSING]'}")
        print(f"GEMINI_API_KEY: {'[SET]' if os.environ.get('GEMINI_API_KEY') else '[MISSING]'}")
        print(f"SMTP_HOST: {'[SET]' if os.environ.get('SMTP_HOST') else '[MISSING]'}")
        print(f"NOTIFICATION_EMAIL_TO: {'[SET]' if os.environ.get('NOTIFICATION_EMAIL_TO') else '[MISSING]'}")

        if not token or not gh_user:
            print("ERROR: GITHUB_TOKEN and GH_USERNAME environment variables are required.")
            sys.exit(1)

        print("\n=== Step 1: Authenticating with GitHub ===")
        gh = Github(token)
        user = gh.get_user()
        print(f"Successfully authenticated as: {user.login}")

        # 1. Discover suitable issue
        print("\n=== Step 2: Searching for Issues ===")
        repo, issue = find_target_issue(gh, language=search_language)
        if not repo or not issue:
            print("No suitable unassigned issue found today. Exiting cleanly (success).")
            return

        print(f"Target repository: {repo.full_name}")
        print(f"Target issue #{issue.number}: {issue.title}")

        # 2. Fork repository to authenticated user
        print(f"\n=== Step 3: Forking Repository to {user.login} ===")
        user_fork = user.create_fork(repo)
        print(f"Fork ready: {user_fork.html_url}")

        # 3. Clone fork locally into temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            clone_url = f"https://x-access-token:{token}@github.com/{user.login}/{repo.name}.git"
            branch_name = f"fix-issue-{issue.number}"

            print(f"\n=== Step 4: Cloning Fork ({user.login}/{repo.name}) ===")
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
            print(f"\n=== Step 5: Planning and Patching with Gemini ===")
            patch_result = plan_and_patch(
                repo_path=temp_dir,
                issue_title=issue.title,
                issue_body=issue.body or ""
            )

            modified = apply_patch(temp_dir, patch_result)
            if not modified:
                print("No files modified by solver. Aborting.")
                return

            # 5. Optional Sandbox Test Execution (e.g. pytest if installed)
            print("\n=== Step 6: Testing Patch ===")
            import shutil
            if shutil.which("pytest"):
                test_code, test_out = run_command(["pytest", "-q"], cwd=temp_dir)
                print(f"Pytest result (exit {test_code}):\n{test_out[:500]}")
            else:
                print("Pytest not installed in runner environment. Skipping local test run.")

            # 6. Commit and Push to Fork
            print("\n=== Step 7: Committing & Pushing Branch ===")
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
            print("\n=== Step 8: Sending Email Notification ===")
            send_review_email(
                issue_title=issue.title,
                issue_url=issue.html_url,
                repo_full_name=repo.full_name,
                fork_branch_url=fork_branch_url,
                diff_summary=diff_snippet or patch_result.get("explanation", "Patch applied."),
                compare_pr_url=compare_pr_url
            )

            print("\n✅ Run completed successfully. Check your email to review and open the PR!")

    except Exception as e:
        print(f"\n❌ UNHANDLED EXCEPTION OCCURRED: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
