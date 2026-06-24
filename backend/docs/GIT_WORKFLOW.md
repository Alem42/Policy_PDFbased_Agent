# Git Workflow

Recommended flow:

```text
master
-> feature branch
-> commit locally
-> push branch
-> pull request / merge request
-> test and review
-> merge back to master
```

Example:

```powershell
git checkout master
git pull
git checkout -b feature/rag-chat
```

Before merging:

```powershell
cd backend
pytest
ruff check app tests
```

Do not commit `.env`, `.venv`, `data/`, cache files, or generated build folders.
