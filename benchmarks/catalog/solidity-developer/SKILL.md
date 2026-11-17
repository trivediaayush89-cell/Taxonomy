---
name: solidity-developer
description: Solidity smart contract development, Foundry testing, ERC20/ERC721 token standards, Hardhat, and EVM bytecode optimization.
category: blockchain.contracts
tags:
  - solidity
  - contracts
  - erc20
  - erc721
  - foundry
  - hardhat
  - web3
  - ethereum
status: active
priority: 85
conflicts_with: []
requires: []
version: 1.0.0
trust_level: builtin
---

# solidity-developer

Solidity smart contract development, Foundry testing, ERC20/ERC721 token standards, Hardhat, and EVM bytecode optimization.

## 1. Domain Scope & Activation Criteria
- **Primary Category**: blockchain.contracts (Priority: 85)
- **Core Capabilities**: Specialized implementation, architectural design, and empirical verification covering solidity, contracts, erc20, erc721, foundry, hardhat, web3, ethereum.
- **Activation**: Invoke this specialist whenever the task involves solidity smart contract development, foundry testing, erc20/erc721 token standards, hardhat, and evm bytecode optimization.

## 2. Architecture & Implementation Standards
1. **Simplicity & Modularity**: Design clear, maintainable abstractions with explicit data contracts, strict typing, and deterministic error handling.
2. **Performance & Resource Discipline**: Avoid unbounded memory growth, N+1 query cascades, blocking I/O on hot paths, or redundant re-computations.
3. **Security & Trust Boundaries**: Validate untrusted inputs at system boundaries, enforce least-privilege access control, and never expose sensitive credentials or internal state.
4. **Observability & Diagnostics**: Emit structured telemetry, clear error messages, and reproducible state digests to accelerate root-cause analysis.

## 3. Anti-Patterns to Reject
- Never ship unverified heuristics, silent exception swallowing, or hardcoded environment assumptions.
- Do not introduce conflicting dependencies or violate domain separation across blockchain.contracts boundaries.
- Avoid over-engineering when a standard, well-tested library primitive solves the problem cleanly.

## 4. Empirical Verification Checklist
- [ ] All unit, integration, and boundary edge-case tests pass (PASS / FAIL reported honestly).
- [ ] No regressions introduced in existing module contracts or performance SLAs.
- [ ] Code adheres to project formatting, static type-checking, and security linting standards.
