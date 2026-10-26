# Git & Azure Databricks Git folders

## Method A (recommended): Existing company Gerrit repository

1. Clone your existing Gerrit repository (if not already cloned).
2. Extract project ZIP as `novacart-azure-poc/` within the repo.
3. From the **existing repo root**, review and commit only the new folder:

```powershell
git status
git add novacart-azure-poc
git diff --cached --stat
git commit -m "feat: scaffold NovaCart Azure Databricks medallion PoC"
git branch --show-current
git remote -v
```

Push to your organization's permitted branch/review ref using your existing Gerrit workflow. If your team uses Gerrit review refs, verify the intended branch before `git push origin HEAD:refs/for/<target-branch>`.

## Method B: New repository on GitHub

Create a new empty private GitHub repository first. Then in PowerShell from the extracted project folder:

```powershell
git init
git switch -c feature/novacart-azure-poc
git add .
git commit -m "feat: scaffold NovaCart Azure Databricks medallion PoC"
git remote add origin https://github.com/<ORG>/<REPO>.git
git push -u origin feature/novacart-azure-poc
```

For GitHub, replace `<ORG>/<REPO>` with the actual repo URL. Authenticate using your configured credential manager, not a pasted secret in the terminal output or repository.

## Later: Connect Databricks to Git

Go to Databricks **Settings → Linked accounts → Add Git credential**, then **Workspace → Create → Git folder** and paste the HTTPS repository URL. Git folders work with supported providers; internal Gerrit installations may require a different integration path or a GitHub/GitLab/Azure DevOps mirror. Configure this in the next implementation stage after the code is pushed.
