---
name: kubernetes-ops
description: Kubernetes manifests, Helm charts, pod deployments, ingress controllers, horizontal pod autoscaling, and service meshes.
category: ops.k8s
tags:
  - kubernetes
  - k8s
  - helm
  - deployment
  - ingress
  - autoscaling
  - cluster
status: active
priority: 80
conflicts_with: []
requires: ["docker-devops"]
version: 1.0.0
trust_level: builtin
---

# kubernetes-ops

Kubernetes manifests, Helm charts, pod deployments, ingress controllers, horizontal pod autoscaling, and service meshes.

## 1. Domain Scope & Activation Criteria
- **Primary Category**: ops.k8s (Priority: 80)
- **Core Capabilities**: Specialized implementation, architectural design, and empirical verification covering kubernetes, k8s, helm, deployment, ingress, autoscaling, cluster.
- **Activation**: Invoke this specialist whenever the task involves kubernetes manifests, helm charts, pod deployments, ingress controllers, horizontal pod autoscaling, and service meshes.

## 2. Architecture & Implementation Standards
1. **Simplicity & Modularity**: Design clear, maintainable abstractions with explicit data contracts, strict typing, and deterministic error handling.
2. **Performance & Resource Discipline**: Avoid unbounded memory growth, N+1 query cascades, blocking I/O on hot paths, or redundant re-computations.
3. **Security & Trust Boundaries**: Validate untrusted inputs at system boundaries, enforce least-privilege access control, and never expose sensitive credentials or internal state.
4. **Observability & Diagnostics**: Emit structured telemetry, clear error messages, and reproducible state digests to accelerate root-cause analysis.

## 3. Anti-Patterns to Reject
- Never ship unverified heuristics, silent exception swallowing, or hardcoded environment assumptions.
- Do not introduce conflicting dependencies or violate domain separation across ops.k8s boundaries.
- Avoid over-engineering when a standard, well-tested library primitive solves the problem cleanly.

## 4. Empirical Verification Checklist
- [ ] All unit, integration, and boundary edge-case tests pass (PASS / FAIL reported honestly).
- [ ] No regressions introduced in existing module contracts or performance SLAs.
- [ ] Code adheres to project formatting, static type-checking, and security linting standards.
