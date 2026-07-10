# Peresvet Agent Instructions

## Repository

Peresvet is a Python 3.12 platform for SCADA, monitoring, data acquisition,
technical object modeling and automation.

Default branch: dev.

## Main domain entities

- objects
- tags
- alerts
- methods
- connectors
- data storages
- schedules

## Architecture

Services live under `src/services`.

Shared infrastructure lives under `src/common`.

Services communicate through RabbitMQ.

Docker Compose is the primary runtime mechanism.

Important infrastructure:

- RabbitMQ
- Redis
- PostgreSQL
- LDAP
- Grafana
- nginx
- VictoriaMetrics

## Rules for all agents

- Keep changes minimal and scoped.
- Branch from `dev`.
- Do not refactor unrelated services.
- Do not change Docker Compose files casually.
- Do not change shared code in `src/common` without checking all affected services.
- Preserve existing service boundaries.
- Add or update tests for behavior changes.
- If tests require Docker services, say exactly which compose stack is needed.
- Never commit secrets or local `.env` values.
- Document changes that affect deployment, backup, LDAP, nginx or compose files.

## Dependency note

The repo contains both `Pipfile`/`Pipfile.lock` and `requirements.txt`.
Before changing dependencies, identify which one is canonical for the affected
workflow and keep dependency files consistent.

## Review policy

For small isolated changes, use:

- implementer
- qa-reviewer
- backend-reviewer, when backend services are touched
- frontend-reviewer, when Grafana Configurator or dashboard behavior is touched

If `src/common` is touched, also use:

- platform-architect

If `src/services/tags` or tag helpers are touched, also use:

- tags-reviewer

If `src/services/dataStorages`, PostgreSQL, VictoriaMetrics or history storage are touched, also use:

- storage-reviewer

If `src/services/connectors` or external protocol behavior is touched, also use:

- connector-reviewer

If Docker, LDAP, nginx, env files, deployment or backup scripts are touched, also use:

- devops-reviewer
- security-reviewer

If auth, secrets, external input, dynamic method execution or privilege boundaries are affected, also use:

- security-reviewer

If public behavior, setup, installation or operations are affected, also use:

- docs-reviewer

Use `test-fixer` only after a concrete test, CI, docs build or Docker validation failure exists.