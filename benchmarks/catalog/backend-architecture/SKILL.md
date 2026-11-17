---
name: backend-architecture
description: High-level backend systems architecture, API design, database schemas, microservices, auth flows, checkout order services, and caching strategies.
category: architecture.system
tags:
  - backend
  - architecture
  - api
  - database
  - microservices
  - auth
  - systems
  - checkout
  - orders
status: active
priority: 85
conflicts_with: []
requires: []
version: 1.0.0
trust_level: builtin
---

# backend-architecture

High-level backend systems architecture, API design, database schemas, microservices, auth flows, checkout order services, and caching strategies.

## 1. Domain Scope & Activation Criteria
- **Primary Category**: architecture.system (Priority: 85)
- **Core Capabilities**: Specialized implementation, architectural design, and empirical verification covering backend, architecture, api, database, microservices, auth, systems, checkout, orders.
- **Activation**: Invoke this specialist whenever the task involves high-level backend systems architecture, api design, database schemas, microservices, auth flows, checkout order services, and caching strategies.

## 2. Architecture & Implementation Standards
1. **Simplicity & Modularity**: Design clear, maintainable abstractions with explicit data contracts, strict typing, and deterministic error handling.
2. **Performance & Resource Discipline**: Avoid unbounded memory growth, N+1 query cascades, blocking I/O on hot paths, or redundant re-computations.
3. **Security & Trust Boundaries**: Validate untrusted inputs at system boundaries, enforce least-privilege access control, and never expose sensitive credentials or internal state.
4. **Observability & Diagnostics**: Emit structured telemetry, clear error messages, and reproducible state digests to accelerate root-cause analysis.

## 3. Anti-Patterns to Reject
- Never ship unverified heuristics, silent exception swallowing, or hardcoded environment assumptions.
- Do not introduce conflicting dependencies or violate domain separation across architecture.system boundaries.
- Avoid over-engineering when a standard, well-tested library primitive solves the problem cleanly.

## 4. Empirical Verification Checklist
- [ ] All unit, integration, and boundary edge-case tests pass (PASS / FAIL reported honestly).
- [ ] No regressions introduced in existing module contracts or performance SLAs.
- [ ] Code adheres to project formatting, static type-checking, and security linting standards.
