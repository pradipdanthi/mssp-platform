# GitHub repository audit (2026-07-28)

## Question

Is [github.com/pradipdanthi/mssp-platform](https://github.com/pradipdanthi/mssp-platform) the same project as `/opt/mssp-control` on VM 100?

## Answer: **No** (before this sync)

| | GitHub `main` (was) | VM 100 `/opt/mssp-control` |
|---|---------------------|----------------------------|
| **History** | 1 commit (`5e6a194`) | KB-001 → KB-082 (full control plane) |
| **Product** | Exported Docker lab stack (Wazuh, OpenSearch, Filebeat, nginx configs) | FastAPI + PostgreSQL + Admin/Customer portals |
| **Purpose** | Snapshot / install helper from **2026-07-06** | Production MSSP control plane + adapter integrations |

The old GitHub tree is **not** wrong for history—it is an **older lab export**, not the current product UI and API.

## What we did locally

1. **Archived** the old GitHub content under  
   `archive/legacy-docker-stack-export-2026-07-06/`  
   with `ARCHIVE_README.md` (reference only).

2. **Repository root** = current MSSP control plane (this project).

3. **Root `README.md`** describes layout, validation, and tags.

4. **`main` branch** merged from `kb039-kb060-platform-roadmap-execution` (includes tag `kb082-soc-alert-taxonomy-validated` on commit `ffbeaaa`).

## Pushing to GitHub

The server needs a **one-time** GitHub SSH key (Deploy key or account key). Public key file:

`/home/secadmin/.ssh/id_ed25519_github_mssp.pub`

After the key is added in GitHub → repo **Settings → Deploy keys** (allow write access), push is run from the control plane host:

```bash
GIT_SSH_COMMAND='ssh -i /home/secadmin/.ssh/id_ed25519_github_mssp -o IdentitiesOnly=yes' \
  git -C /opt/mssp-control push --force-with-lease origin main
GIT_SSH_COMMAND='ssh -i /home/secadmin/.ssh/id_ed25519_github_mssp -o IdentitiesOnly=yes' \
  git -C /opt/mssp-control push origin kb082-soc-alert-taxonomy-validated
```

`--force-with-lease` replaces the old unrelated single-commit `main` with the real project history; legacy files remain under `archive/`.
