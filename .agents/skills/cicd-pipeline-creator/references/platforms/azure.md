# Azure DevOps allowlist

## allowed third-party owners
- Microsoft
- aquase
- trivy
- gitleaks
- github
- sonarsource
- docker

## verified pinned refs
- UsePythonVersion@0
- NodeTool@0
- Cache@2
- PublishPipelineArtifact@1
- PublishTestResults@2
- PublishCodeCoverageResults@2
- DownloadPipelineArtifact@2
- AzureWebApp@1

## required guardrails
- checkout fetchDepth: 0 for secret scanning
- deploy target must be in variable or environment
- production deploys via environment approval
- no echo-only deploy steps
