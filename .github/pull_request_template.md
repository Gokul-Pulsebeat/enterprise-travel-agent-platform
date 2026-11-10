## Related Ticket / PRD

<!-- Required. Link the task PRD under docs/subprojects/. PRs without one will not be reviewed. -->

- PRD: `docs/subprojects/spXX_.../TASK-X.Y_....md`
- Epic: `SPXX`
- Branch:
  `feat/spXX-tYY-...`
  or `chore/spXX-tYY-...` → `productionize`

## Summary of Changes

## <!-- What changed and why, in 2-5 bullets. Link to the acceptance criteria this satisfies. -->

-

## Architectural Impact

<!-- Write "None" with a one-line justification if a category does not apply. Blank answers are not accepted. -->

| Area                                                                         | Impact |
| ---------------------------------------------------------------------------- | ------ |
| **Security** (authN/Z, secrets, PII, new attack surface, injection exposure) |        |
| **Cost** (LLM tokens/model choice, infra, third-party calls)                 |        |
| **Latency** (added hops, startup cost, p95 effect)                           |        |
| **Concurrency** (locking, idempotency, shared state, race conditions)        |        |

**Breaking changes / migration steps:**

<!-- Env vars renamed, schema changes, API contract changes, dependency bumps. Write "None" if none. -->

## Verification

### Checklist

- [ ] Task PRD exists and is linked above
- [ ] New behavior has unit tests; cross-component behavior has integration tests
- [ ] `pytest` passes locally from the repository root
- [ ] Offline/mock mode still works (`LLM_PROVIDER=mock`)
- [ ] No secrets, credentials, or `.env` files committed
- [ ] README, architecture diagrams, and affected docs updated in this PR
- [ ] Naming stays symmetric across flight/hotel (and policy/finops once they exist)
- [ ] Acceptance criteria from the PRD are all met

### Pytest output

<!-- Paste the summary from `pytest -v` (final results lines are enough for long runs). -->

```text
paste pytest output here
```

### Other verification evidence

<!-- Commands run, screenshots, traces, or logs that show the change works. -->
