---
name: mobile-react-native
description: React Native cross-platform mobile development, Expo, mobile gesture navigation, iOS/Android compilation, and native modules.
category: mobile.native
tags:
  - react-native
  - mobile
  - expo
  - ios
  - android
  - native
status: active
priority: 80
conflicts_with: []
requires: ["frontend-ui-engineering"]
version: 1.0.0
trust_level: builtin
---

# mobile-react-native

React Native cross-platform mobile development, Expo, mobile gesture navigation, iOS/Android compilation, and native modules.

## 1. Domain Scope & Activation Criteria
- **Primary Category**: mobile.native (Priority: 80)
- **Core Capabilities**: Specialized implementation, architectural design, and empirical verification covering react-native, mobile, expo, ios, android, native.
- **Activation**: Invoke this specialist whenever the task involves react native cross-platform mobile development, expo, mobile gesture navigation, ios/android compilation, and native modules.

## 2. Architecture & Implementation Standards
1. **Simplicity & Modularity**: Design clear, maintainable abstractions with explicit data contracts, strict typing, and deterministic error handling.
2. **Performance & Resource Discipline**: Avoid unbounded memory growth, N+1 query cascades, blocking I/O on hot paths, or redundant re-computations.
3. **Security & Trust Boundaries**: Validate untrusted inputs at system boundaries, enforce least-privilege access control, and never expose sensitive credentials or internal state.
4. **Observability & Diagnostics**: Emit structured telemetry, clear error messages, and reproducible state digests to accelerate root-cause analysis.

## 3. Anti-Patterns to Reject
- Never ship unverified heuristics, silent exception swallowing, or hardcoded environment assumptions.
- Do not introduce conflicting dependencies or violate domain separation across mobile.native boundaries.
- Avoid over-engineering when a standard, well-tested library primitive solves the problem cleanly.

## 4. Empirical Verification Checklist
- [ ] All unit, integration, and boundary edge-case tests pass (PASS / FAIL reported honestly).
- [ ] No regressions introduced in existing module contracts or performance SLAs.
- [ ] Code adheres to project formatting, static type-checking, and security linting standards.
