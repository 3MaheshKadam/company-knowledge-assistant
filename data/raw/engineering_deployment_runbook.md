# Engineering Runbook: Deployments

## Release Schedule
Production releases happen every Tuesday and Thursday at 14:00 UTC. No deployments are allowed on Fridays or before a public holiday, except emergency hotfixes approved by the engineering director.

## Deployment Steps
Merge the approved pull request into main. The CI pipeline runs lint, unit tests and a security scan. After the pipeline is green, the release engineer triggers the staging deployment and verifies the smoke tests. Production deployment uses a canary rollout, starting at 5 percent of traffic.

## Rollback
If the error rate exceeds 2 percent or p95 latency doubles during the canary, roll back immediately using the one-click rollback in the deploy dashboard. Rollbacks must be announced in the engineering channel within 10 minutes.

## Code Review
Every pull request needs at least 2 approving reviews, and one must come from a code owner. Pull requests larger than 400 changed lines should be split.

## On-Call
On-call rotations last 7 days and start on Monday at 09:00. The on-call engineer receives a stipend of 300 USD per rotation and a day off in lieu after a night incident.
