# Stack defaults

## Node (npm)
- install: `npm ci`
- build: `npm run build`
- test: `npm test -- --coverage`
- artifact: `$(Build.SourcesDirectory)/dist`
- deploy_target: `azure-webapp`

## Node (pnpm)
- install: `pnpm install --frozen-lockfile`
- build: `pnpm build`
- test: `pnpm test`
- artifact: `$(Build.SourcesDirectory)/dist`
- deploy_target: `azure-webapp`

## Python (pip)
- python_version: `3.11`
- install: `python -m pip install -r requirements.txt`
- build: `python -m compileall .`
- test: `pytest -q`
- artifact: `$(Build.SourcesDirectory)/dist`
- deploy_target: `azure-webapp`

## Python + Node (mixed)
- install: `python -m pip install -r requirements.txt && npm ci`
- build: `python -m compileall . && npm run build`
- test: `pytest -q && npm test -- --coverage`
- artifact: `$(Build.SourcesDirectory)/dist`
- deploy_target: `azure-webapp`

## Marker defaults
| marker | default |
| --- | --- |
| `@@PYTHON_VERSION@@` | `3.11` |
| `@@NODE_VERSION@@` | `20` |
| `@@INSTALL_CMD@@` | `python -m pip install -r requirements.txt && npm ci` |
| `@@BUILD_CMD@@` | `python -m compileall . && npm run build` |
| `@@TEST_CMD@@` | `pytest -q && npm test -- --coverage` |
| `@@ARTIFACT_PATH@@` | `$(Build.SourcesDirectory)/dist` |
| `@@DEPLOY_TARGET@@` | `azure-webapp` |

## Scanner rules
- Secret scan: `gitleaks detect --source . --no-banner --redact --log-opts="--all"` with `fetchDepth: 0`.
- Dependency scan: `trivy fs --exit-code 1 --severity HIGH,CRITICAL .`
- Test results: publish JUnit XML and coverage XML.
- Never use `|| true`, `|| exit 0`, or `continue-on-error` on scan/test steps.

## Version source
- Node: `.nvmrc`, `.node-version`, or `package.json` `engines.node`.
- Python: `.python-version` or `pyproject.toml` `requires-python`.
- If no repo evidence exists, use the marker defaults above.