# Platform mapping

The stage structure (build -> scan -> test -> deploy) is the same everywhere; only syntax changes.

| Concept | GitHub Actions | GitLab CI | Azure Pipelines | Jenkins |
|---------|---------------|-----------|-----------------|---------|
| File location | `.github/workflows/pipeline.yml` | `.gitlab-ci.yml` (rename or `include:`) | `azure-pipelines.yml` | `Jenkinsfile` (Groovy, not YAML) |
| Stage order | `needs:` between jobs | `stages:` list + `needs:` | `stages:` + `dependsOn:` | `stage('...')` blocks |
| Run only on main | `if: github.ref == 'refs/heads/main'` | `rules: - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH` | `condition: eq(variables['Build.SourceBranch'], 'refs/heads/main')` | `when { branch 'main' }` |
| Manual approval | `environment:` with required reviewers | `when: manual` | Environment approvals | `input` step |
| Secrets | `${{ secrets.NAME }}` | CI/CD variables (masked, protected) | Variable groups / Key Vault | Credentials binding |
| Cache | `actions/cache` or setup-* `cache:` | `cache:` with key on lockfile | `Cache@2` task | stash / plugin |
| Cloud auth (no static keys) | OIDC `id-token: write` | `id_tokens:` | Workload identity federation | OIDC plugin / agent role |
| Artifacts | `actions/upload-artifact` | `artifacts:` | `PublishPipelineArtifact@1` | `archiveArtifacts` |

## GitLab skeleton
```yaml
stages: [build, scan, test, deploy]
build:
  stage: build
  script: [<INSTALL>, <BUILD>]
  artifacts: { paths: [dist/], expire_in: 1 week }
secret_detection:
  stage: scan
include:
  - template: Security/Secret-Detection.gitlab-ci.yml
  - template: Security/SAST.gitlab-ci.yml
  - template: Security/Dependency-Scanning.gitlab-ci.yml
  - template: Security/Container-Scanning.gitlab-ci.yml
test:
  stage: test
  script: [<TEST_COMMAND>]
deploy_staging:
  stage: deploy
  environment: staging
  rules: [{ if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH' }]
  script: [<DEPLOY>]
deploy_production:
  stage: deploy
  environment: production
  when: manual
  rules: [{ if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH' }]
  script: [<DEPLOY>]
```

## Azure Pipelines skeleton
```yaml
trigger: [main]
stages:
  - stage: Build
    jobs: [{ job: build, steps: [{ script: "<INSTALL> && <BUILD>" }] }]
  - stage: Scan
    dependsOn: Build
    jobs: [{ job: scan, steps: [{ script: "trivy fs --exit-code 1 --severity HIGH,CRITICAL ." }] }]
  - stage: Test
    dependsOn: Build
    jobs: [{ job: test, steps: [{ script: "<TEST_COMMAND>" }] }]
  - stage: Deploy
    dependsOn: [Scan, Test]
    condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
    jobs:
      - deployment: deploy
        environment: production   # approvals configured on the environment
        strategy: { runOnce: { deploy: { steps: [{ script: "<DEPLOY>" }] } } }
```

## Deploy target hints
| Signal in repo | Deploy approach |
|----------------|-----------------|
| `k8s/`, Helm chart | `kubectl apply` / `helm upgrade --install` after OIDC cluster auth |
| `*.tf` | `terraform plan` on PR, `apply` on main with approval |
| `serverless.yml` / SAM `template.yaml` | `serverless deploy` / `sam deploy` |
| Dockerfile only | Push image, then target-specific (ECS, Cloud Run, App Service) |
| `vercel.json` / `netlify.toml` / `fly.toml` | Platform CLI with token secret |
