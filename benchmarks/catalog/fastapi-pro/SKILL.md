---
name: fastapi-pro
description: FastAPI REST APIs, Pydantic v2 schemas, asynchronous routing, dependency injection, and OpenAPI documentation.
category: backend.api
tags:
  - fastapi
  - python
  - pydantic
  - rest
  - api
  - async
  - openapi
status: active
priority: 85
conflicts_with: []
requires: ["backend-architecture"]
version: 1.0.0
trust_level: builtin
---

# fastapi-pro

FastAPI REST APIs, Pydantic v2 schemas, asynchronous routing, dependency injection, and OpenAPI documentation.

## 1. Domain Scope & Activation Criteria
- **Primary Category**: backend.api (Priority: 85)
- **Core Capabilities**: Specialized implementation, architectural design, and empirical verification covering fastapi, python, pydantic, rest, api, async, openapi.
- **Activation**: Invoke this specialist whenever the task involves fastapi rest apis, pydantic v2 schemas, asynchronous routing, dependency injection, and openapi documentation.

## 2. Architecture & Implementation Standards
1. **Simplicity & Modularity**: Design clear, maintainable abstractions with explicit data contracts, strict typing, and deterministic error handling.
2. **Performance & Resource Discipline**: Avoid unbounded memory growth, N+1 query cascades, blocking I/O on hot paths, or redundant re-computations.
3. **Security & Trust Boundaries**: Validate untrusted inputs at system boundaries, enforce least-privilege access control, and never expose sensitive credentials or internal state.
4. **Observability & Diagnostics**: Emit structured telemetry, clear error messages, and reproducible state digests to accelerate root-cause analysis.

## 3. Anti-Patterns to Reject
- Never ship unverified heuristics, silent exception swallowing, or hardcoded environment assumptions.
- Do not introduce conflicting dependencies or violate domain separation across backend.api boundaries.
- Avoid over-engineering when a standard, well-tested library primitive solves the problem cleanly.

## 4. Empirical Verification Checklist
- [ ] All unit, integration, and boundary edge-case tests pass (PASS / FAIL reported honestly).
- [ ] No regressions introduced in existing module contracts or performance SLAs.
- [ ] Code adheres to project formatting, static type-checking, and security linting standards.
