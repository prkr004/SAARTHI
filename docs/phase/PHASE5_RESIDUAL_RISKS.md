# Phase 5 Residual Risks

Date: 2026-04-07

## Open Risks

1. Python runtime compatibility warning
- Current local runtime may emit LangChain/Pydantic v1 warning under Python 3.14.
- Mitigation: standardize production runtime to Python 3.12.

2. Model service dependency
- API answer paths depend on local/remote model availability.
- Mitigation: monitor model readiness and maintain startup checks.

3. Vector index freshness
- RAG quality depends on index freshness after source document changes.
- Mitigation: include index rebuild in document update runbook.

## Risk Acceptance

No residual risks currently block normal operation of FastAPI + React when controls are followed.
