# Git failure classes

Use these as hypotheses, not labels to force onto every error.

| Likely class | Distinguishing evidence | Small safe next step |
| --- | --- | --- |
| `NOT_A_GIT_REPOSITORY` | `git rev-parse --show-toplevel` fails outside a worktree | Locate the intended repository; do not create a replacement directory. |
| `NO_ORIGIN` | `git remote get-url origin` reports no such remote | Check other remotes and project metadata; request a URL if none is trusted. |
| `WRONG_REMOTE` | Origin differs from a verified canonical URL or trusted project metadata | Confirm the mismatch causes the failure before changing only origin. |
| `REMOTE_REPOSITORY_NOT_FOUND` | Server responds that the repository is absent or inaccessible | Check exact URL and access; an authentication failure can look similar. |
| `AUTHENTICATION_FAILED` | Server rejects credentials or permissions | Check the account, credential helper, and repository access without deleting credentials. |
| `DNS_FAILED` | Git cannot resolve the remote or proxy hostname | Check name resolution for the host Git actually uses; do not rewrite origin. |
| `NETWORK_UNREACHABLE` | Route, timeout, or connection failure after name resolution | Check reachability and network path before changing Git config. |
| `PROXY_MISCONFIGURED` | Git selects a stale or unreachable proxy | Inspect config source, proxy process, and listening port; try a command-scoped setting first. |
| `TLS_FAILED` | Certificate or TLS handshake error after connection | Inspect certificates, interception, and Git's TLS backend; keep SSL verification enabled. |
| `NON_FAST_FORWARD` | Push rejects because remote tip is not an ancestor of the local branch | Fetch, then compare tips and merge bases before integrating. |
| `LOCAL_REMOTE_DIVERGENCE` | Both sides have commits absent from the other after fetch | Show both commit ranges and choose a preservation-safe integration path. |
| `DETACHED_HEAD` | `git symbolic-ref --quiet --short HEAD` fails | Identify the intended branch and protect any commits made while detached. |
| `UNCOMMITTED_WORK_BLOCKING_OPERATION` | Git refuses checkout, merge, or pull because local changes would be overwritten | Preserve those changes; do not reset, clean, or stash them by default. |

