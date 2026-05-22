---
name: safe-commit
description: A strict agentic workflow for performing secure Git commits. Use this skill whenever you are asked to commit changes to a repository, especially before making it public. It enforces a manual review of staged files and runs an automated check to prevent accidental leakage of credentials, secrets, or sensitive configuration files.
---

# Safe Commit

## Overview
The `safe-commit` skill ensures that every commit is preceded by a rigorous security check. It is designed to catch sensitive files like service account JSONs, `.env` files, and API keys before they reach the Git history.

## Workflow: The Security Checkpoint
When this skill is active and you are preparing to commit, you MUST follow these steps sequentially:

### 1. Stage and Automated Check
1. Stage the files intended for the commit: `git add <file1> <file2>`.
2. Run the automated check script: `node safe-commit/scripts/check_secrets.cjs`.
   - If the script fails, **stop immediately**, unstage the sensitive files, and inform the user.

### 2. Manual Inspection
1. Run `git status` to verify the list of staged files.
2. Run `git diff --staged` to inspect the actual code changes. 
3. **Search the diff for any hardcoded strings** that look like API keys, project IDs, or passwords.

### 3. Verify Against Prohibited Files
Confirm that **NONE** of the following are in the "Changes to be committed" list:
- Service Account keys (e.g., `*.json`)
- API key storage (e.g., `*_credentials.txt`)
- Local development plans containing internal details (e.g., `GCP_DEPLOYMENT.md`)
- AI development tools and skills (e.g., `.gemini/`, `*.skill`)

### 4. Final Confirmation
You must explicitly output the following statement before running the `git commit` command:
> "SECURITY CHECK: I have verified that no sensitive files (JSON keys, env files, or plain-text secrets) are staged for this commit."

### 5. Commit
Use a clear, concise commit message.

## Resources

### scripts/check_secrets.cjs
An automated script that scans staged files for common sensitive file patterns (JSON, ENV, PEM, etc.). Always run this before committing.
