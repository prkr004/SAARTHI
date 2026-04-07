# Post-Launch Monitoring Checklist

Date: 2026-04-07

## API Health

- [ ] `/api/v1/health/live` returns 200
- [ ] `/api/v1/health/ready` returns 200
- [ ] Error rate, p95 latency, and timeout rates are within target

## Application Flows

- [ ] Register and login flow succeeds
- [ ] Conversation create/rename/delete succeeds
- [ ] Ask flow returns grounded answer with sources
- [ ] Temporal ask flow returns stable metadata payload

## Model and Retrieval

- [ ] Selected model is available and responsive
- [ ] Vector index path is present and readable
- [ ] Source labels and links render correctly in frontend

## Operations

- [ ] Logs include request ID and actionable error context
- [ ] Alerts configured for API downtime and elevated 5xx rates
- [ ] Runbook links and owner contacts are up to date
