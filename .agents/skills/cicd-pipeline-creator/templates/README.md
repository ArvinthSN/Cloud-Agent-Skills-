# CI/CD Platform Templates

| Platform | Template | Native location |
|---|---|---|
| GitHub Actions | `github/pipeline.yml` | `.github/workflows/pipeline.yml` |
| GitLab CI/CD | `gitlab/.gitlab-ci.yml` | Repository root |
| Azure DevOps | `azure/azure-pipelines.yml` | Repository root |
| Jenkins | `jenkins/Jenkinsfile` | Repository root |
| CircleCI | `circleci/config.yml` | `.circleci/config.yml` |

Jenkins uses a Groovy Jenkinsfile natively, not YAML. GitHub Actions, GitLab CI, Azure DevOps, and CircleCI use YAML or YAML-like configuration.

These are starter templates. Replace every TODO and `<...>` placeholder with commands and paths detected from the repository. Configure real scanners and deployment steps, store credentials in the platform's secret store, and validate with the relevant platform tools before use.

Recommended skill workflow: inspect repository -> detect platform -> resolve multiple-platform ambiguity -> detect stack and tests -> select template -> fill project-specific commands -> validate -> deliver to a repo-local output directory such as `./outputs/`.
