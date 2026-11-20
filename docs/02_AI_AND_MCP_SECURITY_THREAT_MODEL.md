# 02 — AI and MCP Security Threat Model

| Field               | Value                                                                                                                                                                                                                   |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Status              | Living document; planned ahead of the epics that implement it. Reviewed at the start of every epic and whenever an OWASP list changes                                                                                   |
| Scope               | The agent, the MCP layer, the policy RAG, the code sandbox and the REST services, as planned in [`00_MASTER_PRD.md`](00_MASTER_PRD.md)                                                                                  |
| Standing constraint | **Nothing may cost money.** Every control, tool and test below is open source or runs inside a free tier (see section 8)                                                                                                |
| Related             | [`TASK-0.6`](subprojects/sp00_platform_and_dx/TASK-0.6_sbom_generation_and_validation.md) (SBOM), [`TASK-0.4`](subprojects/sp00_platform_and_dx/TASK-0.4_api_logging_foundation.md) (audit logging), SP03 to SP06 epics |

---

## 1. Purpose

This is a portfolio project, and the security of an agentic system is part of what it demonstrates. The flight and hotel tools are our own and take no external input, so the **real** risk today is small. The goal of this document is to design and prove the defenses **as if that were not true**: as if the MCP servers were third-party services of unknown trustworthiness, and as if every piece of text the model reads could be hostile.

## 2. Ground Rules

| #   | Rule                                                                                                                                                                                                                                              |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | **Zero cost.** Only open-source tools and free tiers. CI never calls a paid LLM; adversarial tests use a mock provider, and any model-in-the-loop evaluation uses local models                                                                    |
| R2  | **The MCP layer is external.** From the agent's point of view every MCP server, including `flight_mcp_server` and `hotel_mcp_server`, is an untrusted third party. The agent verifies, constrains and monitors it; it never relies on it behaving |
| R3  | **Data is never instructions.** Tool descriptions, tool results, retrieved documents and user text are data. Nothing found inside them can add tools, change goals or authorize actions                                                           |
| R4  | **Deterministic controls gate; model judgment does not.** A defense that depends on the LLM noticing an attack is not a control. Controls are code that runs the same way every time and can be tested without a model                            |
| R5  | **Assume the model can be fooled.** Design so that a successful injection still cannot do real harm: least privilege, scoped tools, human approval for consequential actions, budgets                                                             |
| R6  | **Evidence over assertion.** Each control has an automated test that fails if the control is removed, traceable to a scenario ID in section 7                                                                                                     |
| R7  | **Defense in depth.** No single layer (intent router, sanitizer, validator, approval) is relied on alone                                                                                                                                          |

## 3. System, Trust Boundaries and Untrusted Inputs

```text
   User / API client
          |
          v                                   (1) UNTRUSTED: user text
 +--------------------+
 | Ingress guardrail  |  JWT, rate limit, PII redaction, intent router, injection screen
 +---------+----------+
           v
 +-----------------------------------------------+
 | LangGraph supervisor + sub-agents (LLM)       |  (2) UNTRUSTED: model output
 | typed state, checkpointer, HITL interrupts    |
 +---------+-------------------------------------+
           |
 ==========|=====================  TRUST BOUNDARY: the MCP client treats every server as external  =====
           v
 +-----------------------------------------------+
 | MCP client policy layer (agent side)          |  allowlist, identity, manifest pin, validation,
 | owns tool descriptions, scopes, budgets       |  size/time limits, demarcation, audit
 +---------+-------------------------------------+
           |  Streamable HTTP, audience-bound token
           v
 +---------------+  +---------------+  +---------------+  +---------------+
 | flight_mcp    |  | hotel_mcp     |  | policy_mcp    |  | finops_mcp    |   (3) UNTRUSTED: tool
 +-------+-------+  +-------+-------+  +-------+-------+  +-------+-------+       metadata and results
         v                  v                  v                  v
     flight_api         hotel_api       Postgres/pgvector     Code sandbox     (4) UNTRUSTED: retrieved
                                                                                    policy documents
          ^
          |  every hop: structured audit logs and traces (SP00 TASK-0.4, TASK-0.5)
```

**Untrusted inputs, all treated as hostile:** (1) user messages; (2) LLM output; (3) tool names, descriptions, parameter schemas, defaults, annotations and results from any MCP server; (4) retrieved policy documents and anything else read into a prompt.

**Assets:** booking integrity and money-like workflows (SP02), employee identity and role tiers, corporate policy content, credentials and tokens, the LLM budget (free-tier limits), the integrity of agent state, and the reputation of the platform's answers.

**Adversaries considered:** a malicious or careless user; an attacker who controls content the agent reads (a poisoned document or tool result); a compromised or malicious MCP server or package (modeled even though ours are not); a compromised dependency or base image; an over-eager agent acting beyond its mandate.

## 4. Standards Used

| Standard                                       | Edition and status                                                                                                             | Use here                                     |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------- |
| **OWASP Top 10 for LLM Applications**          | **2026 edition (published August 2026)**; most entries renumbered and "System Prompt Leakage" is now "Hidden Context Exposure" | Section 6.1; IDs below are the 2026 IDs      |
| **OWASP Top 10 for Agentic Applications**      | 2026 edition (ASI01 to ASI10, published December 2025)                                                                         | Section 6.2                                  |
| **OWASP MCP Top 10**                           | Beta; wording and numbering may change                                                                                         | Cross-referenced in section 6.3 where stable |
| **MCP specification, security best practices** | Current spec: confused deputy, token passthrough, SSRF, session hijacking, local-server compromise, scope minimization         | Section 6.3                                  |

IDs were checked against the official repositories and project pages when this document was written. Earlier planning notes in this repository may mention the 2025 LLM list; **the 2026 numbering is authoritative from here**. Re-verify the IDs whenever a list is revised.

## 5. Control Catalog

Each control has an ID, an owner task, and (section 7) a test. "Owner" is the epic task that implements it; tasks marked _new_ are added to the epic PRDs by this planning change.

| ID   | Control                                                                                                                                                                                                                                  | Owner                                          |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------- |
| C-01 | **Agent-owned tool descriptions.** The model sees descriptions and schemas authored and versioned in this repository. Remote descriptions are never forwarded to the model verbatim; they are data used only for change detection (C-03) | SP03 TASK-3.7 _(new)_                          |
| C-02 | **Server allowlist and identity.** Only allow-listed server URLs, HTTPS with certificate verification, no redirects to other hosts, Cloud Run identity (audience-bound ID token) for service-to-service calls                            | SP03 TASK-3.7 _(new)_, TASK-3.2                |
| C-03 | **Tool manifest pinning.** A reviewed lock file records a hash of each tool's name, description and input schema. A mismatch at connect time or mid-session quarantines the tool and alerts (defeats rug pulls and late poisoning)       | SP03 TASK-3.7 _(new)_                          |
| C-04 | **Namespacing.** Tools are addressed as `server.tool`; a duplicate or shadowing name from another server is rejected                                                                                                                     | SP03 TASK-3.7 _(new)_                          |
| C-05 | **Static scan of tool metadata.** Reject hidden Unicode (zero-width, bidirectional controls), control and ANSI characters, instruction-like patterns, embedded URLs and over-long text in names, descriptions, parameters and defaults   | SP03 TASK-3.7 _(new)_                          |
| C-06 | **Result validation and limits.** Validate every result against an expected schema, cap size, depth and time, accept only allowed content types, strip control characters, and enforce per-call and per-run timeouts                     | SP03 TASK-3.7 _(new)_                          |
| C-07 | **Untrusted-content handling.** Results stay in data fields, are demarcated (datamarking or spotlighting) when shown to a model, are screened for instruction patterns, and **never** become plan authority                              | SP03 TASK-3.6, TASK-3.7; SP04 TASK-4.6 _(new)_ |
| C-08 | **Argument validation and egress DLP.** Arguments are validated against allow-listed shapes and values, no free-form URLs, secrets and personal data scrubbed before any call leaves the agent                                           | SP03 TASK-3.4, TASK-3.7 _(new)_                |
| C-09 | **Identity and least privilege.** Short-lived JWT, audience-bound to one server, **no token passthrough** (a server never forwards a received token downstream), per-tool scopes, per-sub-agent tool allow-lists                         | SP03 TASK-3.2, TASK-3.7; SP04 TASK-4.3         |
| C-10 | **Transport hardening.** HTTPS only, `Origin` and `Host` validation, no wildcard CORS, request size and time limits, per-identity rate limits                                                                                            | SP03 TASK-3.1, TASK-3.3                        |
| C-11 | **Human approval and our own tool policy.** State-changing or high-impact tools require approval; read-only versus state-changing is decided by **our** policy table, never by a server's own hints (`readOnlyHint` and similar)         | SP04 TASK-4.5, TASK-4.6 _(new)_                |
| C-12 | **Run budgets.** Maximum steps, tool calls, tokens, wall time and spend per run, user and day, with a loop breaker                                                                                                                       | SP04 TASK-4.6 _(new)_; SP06 TASK-6.7 _(new)_   |
| C-13 | **State integrity.** Provenance-tagged messages (user, tool, system), schema-validated checkpoints, bounded history, no raw tool text promoted to system context                                                                         | SP04 TASK-4.1, TASK-4.2, TASK-4.6 _(new)_      |
| C-14 | **Inter-agent contracts.** Agents exchange typed, validated structures, never free-text commands                                                                                                                                         | SP04 TASK-4.4, TASK-4.6 _(new)_                |
| C-15 | **Output handling and egress validation.** Deterministic groundedness verifier, PII and secret filters, and model output is never executed, rendered as markup, or interpolated into queries                                             | SP06 TASK-6.3, TASK-6.7 _(new)_                |
| C-16 | **Hidden-context hygiene.** Prompts contain no secrets, tokens or internal URLs; prompt-extraction attempts are tested; the system prompt is treated as recoverable                                                                      | SP06 TASK-6.7 _(new)_                          |
| C-17 | **RAG integrity.** Ingest only from an allow-listed, hashed source; scrub instruction-like content; enforce retrieval access by role tier; require citations; screen for embedding outliers                                              | SP05 TASK-5.6 _(new)_                          |
| C-18 | **Sandbox hardening.** No network, read-only filesystem, no secrets, CPU, memory and time limits, output size cap, numeric results re-validated                                                                                          | SP05 TASK-5.4, TASK-5.6 _(new)_                |
| C-19 | **Audit trail.** Every tool call and every control decision is logged (tool, redacted arguments, result size and hash, decision) with trace correlation                                                                                  | SP00 TASK-0.4 and TASK-0.5; SP03 TASK-3.7      |
| C-20 | **Supply chain.** Pinned dependencies, SBOM generated, validated and scanned in CI and CD, AI-BOM listing every model, prompt, tool and dataset                                                                                          | SP00 TASK-0.6; SP06 TASK-6.6 _(new)_           |
| C-21 | **Adversarial regression suite.** A malicious MCP server fixture and deterministic tests (section 7) run in CI and fail if any control regresses                                                                                         | SP03 TASK-3.8 _(new)_                          |
| C-22 | **Red-team evaluation.** Open-source scanners run against the agent with local models, reported but not gating (non-deterministic)                                                                                                       | SP06 TASK-6.7 _(new)_                          |
| C-23 | **Kill switches.** Any tool or server can be disabled by configuration without a deploy of code                                                                                                                                          | SP04 TASK-4.6 _(new)_                          |

## 6. Mapping to the Standards

### 6.1 OWASP Top 10 for LLM Applications (2026)

| ID    | Risk                             | How it applies here                                                                  | Controls                                         | Evidence                             |
| ----- | -------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------ | ------------------------------------ |
| LLM01 | Prompt Injection                 | Direct (user text) and indirect (tool results, policy documents, tool metadata)      | C-01, C-05, C-07, C-13, plus SP03 intent router  | S-01, S-02, S-05, S-07               |
| LLM02 | Sensitive Information Disclosure | Booking, identity and policy data could leak through answers, tool arguments or logs | C-08, C-15, C-16, C-17; log redaction (TASK-0.4) | S-08; redaction tests                |
| LLM03 | Excessive Agency                 | An agent calling tools it should not, or acting without approval                     | C-09, C-11, C-12, C-23                           | S-12, S-13; scope and approval tests |
| LLM04 | Supply Chain                     | Compromised packages, base images, MCP servers, model providers                      | C-02, C-03, C-20                                 | SBOM gate; S-11                      |
| LLM05 | Data and Model Poisoning         | Poisoned policy documents or evaluation data; tampered tool definitions              | C-03, C-17                                       | S-03; ingestion tests                |
| LLM06 | Unbounded Consumption            | Loops, huge outputs, expensive prompts, retry storms; the free-tier budgets          | C-06, C-10, C-12                                 | S-06, S-10; budget tests             |
| LLM07 | Misinformation                   | Invented prices, flight numbers or policy statements                                 | C-15 (groundedness verifier), C-17 citations     | SP06 golden set                      |
| LLM08 | Hidden Context Exposure          | Prompts leaking instructions, tokens or internal URLs                                | C-16                                             | Prompt-extraction tests              |
| LLM09 | Vector and Embedding Weaknesses  | Policy retrieval returning poisoned or unauthorized content                          | C-17                                             | Retrieval ACL and outlier tests      |
| LLM10 | Improper Output Handling         | Model output reaching a database query, the sandbox, a template or a downstream tool | C-08, C-15, C-18                                 | Output-handling tests                |

### 6.2 OWASP Top 10 for Agentic Applications (2026)

| ID    | Risk                                 | Controls                                                                                                         | Owner                                       |
| ----- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| ASI01 | Agent Goal Hijack                    | C-07, C-13, plan validation against the original request and allowed tool graph                                  | SP04 TASK-4.6                               |
| ASI02 | Tool Misuse and Exploitation         | C-08, C-09, C-11, C-12                                                                                           | SP03 TASK-3.7; SP04 TASK-4.6                |
| ASI03 | Identity and Privilege Abuse         | C-09, C-02                                                                                                       | SP03 TASK-3.2, TASK-3.7                     |
| ASI04 | Agentic Supply Chain Vulnerabilities | C-02, C-03, C-04, C-20                                                                                           | SP03 TASK-3.7; SP00 TASK-0.6; SP06 TASK-6.6 |
| ASI05 | Unexpected Code Execution            | C-18, C-15                                                                                                       | SP05 TASK-5.4, TASK-5.6                     |
| ASI06 | Memory and Context Poisoning         | C-13, C-17                                                                                                       | SP04 TASK-4.6; SP05 TASK-5.6                |
| ASI07 | Insecure Inter-Agent Communication   | C-14                                                                                                             | SP04 TASK-4.4, TASK-4.6                     |
| ASI08 | Cascading Failures                   | C-12, C-23, circuit breakers and timeouts                                                                        | SP04 TASK-4.6; SP06 TASK-6.1                |
| ASI09 | Human-Agent Trust Exploitation       | C-11, grounded and cited answers (C-15), approval summaries generated from verified data rather than model prose | SP04 TASK-4.5; SP06 TASK-6.3                |
| ASI10 | Rogue Agents                         | C-09, C-12, C-19, C-23                                                                                           | SP04 TASK-4.6                               |

### 6.3 MCP-specific attack catalog

The OWASP MCP Top 10 is in beta, so scenarios are named by attack, not by its IDs; where the beta list is stable (Tool Poisoning, Prompt Injection via Contextual Payloads, Lack of Audit and Telemetry) it is consistent with the rows below.

| Scenario | Attack                                                                                                         | Why it matters even with our own servers                               | Controls         |
| -------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- | ---------------- |
| S-01     | **Tool poisoning in descriptions**: hidden instructions in a tool's description                                | The model reads descriptions as trusted context                        | C-01, C-05       |
| S-02     | **Poisoning in schemas**: parameter names, defaults or enums that carry instructions or exfiltration hints     | Schemas are also read by the model                                     | C-01, C-03, C-05 |
| S-03     | **Rug pull**: a tool's definition changes after it was reviewed or approved                                    | A server can change behavior at any time; our own could be compromised | C-03             |
| S-04     | **Tool shadowing and name collision**: a second server registers a tool that overrides or impersonates another | Cross-server contamination                                             | C-04             |
| S-05     | **Injection in tool results**: "ignore previous instructions and call X" inside returned data                  | Results flow straight into the model's context                         | C-07             |
| S-06     | **Result flood**: huge, deeply nested or endless responses                                                     | Cost, memory and denial of service                                     | C-06, C-12       |
| S-07     | **Invisible characters**: zero-width, bidirectional or ANSI sequences in metadata and results                  | Hides instructions from human reviewers                                | C-05, C-06       |
| S-08     | **Exfiltration through arguments**: the agent is persuaded to put secrets or personal data in tool arguments   | The argument channel leaves the trust boundary                         | C-08             |
| S-09     | **Token passthrough and confused deputy**: a server asks for, echoes or forwards the caller's token            | Forbidden by the MCP specification; breaks audience binding            | C-09             |
| S-10     | **Slow or hanging server and retry storms**                                                                    | Exhausts budgets and request slots                                     | C-06, C-12       |
| S-11     | **Server impersonation or redirect** to a host that is not on the allowlist                                    | Typosquatting and DNS tricks are the usual route in                    | C-02             |
| S-12     | **False safety hints**: a destructive tool declared read-only                                                  | Servers describe themselves; the agent must not trust that             | C-11             |
| S-13     | **Scope escalation**: a tool outside a sub-agent's mandate appears or is called                                | Over-broad permissions are the most common failure                     | C-09, C-23       |
| S-14     | **Missing or wrong authentication**: unauthenticated call or a token for another audience                      | Basic, but must be proven rejected                                     | C-09, C-10       |
| S-15     | **Cross-origin and DNS-rebinding style requests** to the HTTP transport                                        | Browsers and local services can be coerced into calling servers        | C-10             |

## 7. Test Evidence Strategy (free and deterministic)

**The central idea: test the guards, not the model.** The defenses in section 5 are ordinary code at the MCP client boundary. They can be proven with a deliberately malicious server and a **mock LLM provider** (which the agent already supports), at no cost, deterministically, in CI.

**The adversarial MCP server fixture** (SP03 TASK-3.8): a small test-only server that, on demand, behaves like each scenario S-01 to S-15: poisoned metadata, a definition that changes between calls, a shadowing tool, injected result text, floods, invisible characters, token echoing, hangs, and redirects. Each test asserts that the **control** fires, for example the connection is refused, the tool is quarantined, the content is demarcated or rejected, the call is blocked or the budget stops the run. Test names carry the scenario ID (`test_s03_rug_pull_is_quarantined`) so coverage of the catalog is auditable, and a test fails if its control is removed.

| Layer                                       | Gates CI? | Cost | Purpose                                                                                                                                                                                                                                  |
| ------------------------------------------- | --------- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Deterministic scenario tests (S-01 to S-15) | **Yes**   | $0   | Prove each client-side control with the malicious server and a mock LLM                                                                                                                                                                  |
| Unit tests of validators and scanners       | **Yes**   | $0   | Edge cases: Unicode, size limits, schema failures, expiry                                                                                                                                                                                |
| Redaction and prompt-hygiene tests          | **Yes**   | $0   | No secrets or personal data in logs, prompts or arguments (sentinel-secret technique)                                                                                                                                                    |
| Red-team evaluation with local models       | No        | $0   | Open-source scanners (for example garak, promptfoo, PyRIT; confirm each license at adoption) run against a local model through Ollama; results are tracked over time and reviewed, never gate a merge because they are non-deterministic |

## 8. Zero-Cost Register

| Item                                        | Why it is free                                                                                   | Watch                                                             |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------- |
| GitHub Actions for all tests and scans      | Free allowance (private repositories: 2,000 minutes a month; public: unlimited standard runners) | Path-filter heavy jobs; record added minutes in each task         |
| Mock LLM provider for all gating tests      | No API calls                                                                                     | Keep the mock able to simulate hostile model behavior             |
| Local models through Ollama for evaluations | Runs on the developer's machine                                                                  | Non-gating; results are advisory                                  |
| Open-source scanners and validators         | Syft, Grype, CycloneDX CLI, sbomqs, and the red-team tools are open source                       | Pin versions; confirm licenses at adoption                        |
| Redis for rate limits and budgets           | Free tier already provisioned in SP01                                                            | Check the free quota before enabling per-request counters         |
| Observability                               | Free tiers, with the cost analysis in TASK-0.4 and TASK-0.5                                      | Alerting charges are a known future cost; see TASK-0.5            |
| Signed attestations                         | Free only for public repositories on current plans                                               | Conditional in TASK-0.6                                           |
| **Not used**                                | Paid LLM APIs in CI, hosted scanning platforms, GitHub Advanced Security on private repositories | Any proposal to use one needs an explicit decision, not a default |

## 9. Residual Risk and Accepted Limits

- **Sophisticated prompt injection can still persuade a model.** No filter makes this impossible. The design therefore limits the damage: least privilege, scoped tools, our own tool policy, human approval for consequential actions, budgets and kill switches.
- **Today's tools are read-only.** The flight and hotel tools search and fetch. The blast radius grows when bookings arrive (SP02) and when tools that change state are exposed to the agent, which is why C-11 (approval) and C-12 (budgets) are required before any such tool is reachable.
- **Heuristic detectors have false negatives.** Instruction-pattern and anomaly detection are defense in depth only; the structural controls (C-01, C-03, C-07) carry the weight.
- **A compromised dependency can defeat in-process controls.** The SBOM and vulnerability gate reduce this; they do not eliminate it.
- **The non-gating red-team results are advisory** and depend on the local models used.

## 10. Ownership and Review

| Epic | Carries                                                                                                                                                  |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SP00 | Audit logging and telemetry (TASK-0.4, TASK-0.5); SBOM and supply-chain gate (TASK-0.6)                                                                  |
| SP02 | Transactional integrity and identity that later controls depend on                                                                                       |
| SP03 | The MCP trust boundary (TASK-3.7), the adversarial harness and regression suite (TASK-3.8), authentication, rate limits, intent router, output screening |
| SP04 | Agent-level controls (TASK-4.6): scoping, approval, state integrity, inter-agent contracts, budgets and kill switches                                    |
| SP05 | RAG and sandbox security (TASK-5.6)                                                                                                                      |
| SP06 | Egress validation, hidden-context and consumption controls and red-team evaluation (TASK-6.7), and the AI-BOM (TASK-6.6)                                 |

**Review cadence:** at the start of each epic, check the OWASP editions and the MCP security guidance for changes, update the mapping tables and add scenarios; each epic's pull request records which controls and scenarios it delivers.
