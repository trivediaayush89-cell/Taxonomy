---
name: security-scanner
description: Static application security testing (SAST), dependency vulnerability scanning, OWASP top 10 auditing, and secrets detection.
category: security.appsec
tags:
  - security
  - sast
  - owasp
  - vulnerabilities
  - auth
  - cve
  - audit
status: active
priority: 85
conflicts_with: []
requires: []
version: 1.0.0
trust_level: builtin
---

# security-scanner

Static application security testing (SAST), dependency vulnerability scanning, OWASP top 10 auditing, and secrets detection.

## 1. Domain Scope & Activation Criteria
- **Primary Category**: security.appsec (Priority: 85)
- **Core Capabilities**: Specialized implementation, architectural design, and empirical verification covering security, sast, owasp, vulnerabilities, auth, cve, audit.
- **Activation**: Invoke this specialist whenever the task involves static application security testing (sast), dependency vulnerability scanning, owasp top 10 auditing, and secrets detection.

## 2. Architecture & Implementation Standards
1. **Simplicity & Modularity**: Design clear, maintainable abstractions with explicit data contracts, strict typing, and deterministic error handling.
2. **Performance & Resource Discipline**: Avoid unbounded memory growth, N+1 query cascades, blocking I/O on hot paths, or redundant re-computations.
3. **Security & Trust Boundaries**: Validate untrusted inputs at system boundaries, enforce least-privilege access control, and never expose sensitive credentials or internal state.
4. **Observability & Diagnostics**: Emit structured telemetry, clear error messages, and reproducible state digests to accelerate root-cause analysis.

## 3. Anti-Patterns to Reject
- Never ship unverified heuristics, silent exception swallowing, or hardcoded environment assumptions.
- Do not introduce conflicting dependencies or violate domain separation across security.appsec boundaries.
- Avoid over-engineering when a standard, well-tested library primitive solves the problem cleanly.

## 4. Empirical Verification Checklist
- [ ] All unit, integration, and boundary edge-case tests pass (PASS / FAIL reported honestly).
- [ ] No regressions introduced in existing module contracts or performance SLAs.
- [ ] Code adheres to project formatting, static type-checking, and security linting standards.
