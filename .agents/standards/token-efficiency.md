# Token-efficient context policy

Reduce irrelevant context without omitting facts required for correctness or safety.

## Progressive loading

1. Load the selected skill overview.
2. Inspect project manifests, entry points and configuration relevant to the task.
3. Load only the reference sections required.
4. Reuse validated structured facts across skill handoffs.
5. Load deeper source files only when evidence points to them.

## Scan boundaries

Exclude by default:
- VCS metadata (.git);
- dependency trees (node_modules, .venv, venv, vendor folders);
- caches and bytecode (__pycache__, .pytest_cache, .mypy_cache);
- build output (dist, build, target, coverage output);
- Terraform state, plans and .terraform;
- binaries and files above a configurable size threshold.

Never follow symlinks outside the selected repository root unless explicitly required.

## Bounded outputs

- Prefer summaries and file references over full contents.
- Keep file samples, diagnostics and evidence excerpts capped.
- Deduplicate repeated findings.
- Include omitted item counts when truncated.
- Do not repeat unchanged context in every skill response.
- Store detailed logs as artifacts; return a concise summary and path.

## Cache validity

A cached project summary is reusable only when it identifies:
- repository root;
- scan timestamp or revision;
- scanner/schema version;
- relevant project paths.

Re-scan when repository revision or relevant manifests change. Do not treat an unversioned summary as authoritative.

## Safety over savings

Never omit approval gates, secret checks, error details needed to fix a failure, or evidence needed to justify a recommendation merely to save tokens.
