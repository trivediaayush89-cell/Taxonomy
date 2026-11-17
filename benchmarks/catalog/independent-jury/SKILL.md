---
name: independent-jury
description: Adversarial multi-agent courtroom and independent architectural review challenging systems assumptions and empirical implementations.
category: decision.review
tags:
  - review
  - jury
  - courtroom
  - architecture-review
  - adversarial
  - audit
  - judge
status: active
priority: 90
conflicts_with: []
requires: []
version: 1.0.0
trust_level: builtin
---

# independent-jury

Adversarial multi-agent courtroom and independent architectural review challenging systems assumptions and empirical implementations.

## 1. Domain Scope & Activation Criteria
- **Primary Category**: decision.review (Priority: 90)
- **Core Capabilities**: Specialized implementation, architectural design, and empirical verification covering review, jury, courtroom, architecture-review, adversarial, audit, judge.
- **Activation**: Invoke this specialist whenever the task involves adversarial multi-agent courtroom and independent architectural review challenging systems assumptions and empirical implementations.

## 2. Architecture & Implementation Standards
1. **Simplicity & Modularity**: Design clear, maintainable abstractions with explicit data contracts, strict typing, and deterministic error handling.
2. **Performance & Resource Discipline**: Avoid unbounded memory growth, N+1 query cascades, blocking I/O on hot paths, or redundant re-computations.
3. **Security & Trust Boundaries**: Validate untrusted inputs at system boundaries, enforce least-privilege access control, and never expose sensitive credentials or internal state.
4. **Observability & Diagnostics**: Emit structured telemetry, clear error messages, and reproducible state digests to accelerate root-cause analysis.

## 3. Anti-Patterns to Reject
- Never ship unverified heuristics, silent exception swallowing, or hardcoded environment assumptions.
- Do not introduce conflicting dependencies or violate domain separation across decision.review boundaries.
- Avoid over-engineering when a standard, well-tested library primitive solves the problem cleanly.

## 4. Empirical Verification Checklist
- [ ] All unit, integration, and boundary edge-case tests pass (PASS / FAIL reported honestly).
- [ ] No regressions introduced in existing module contracts or performance SLAs.
- [ ] Code adheres to project formatting, static type-checking, and security linting standards.
