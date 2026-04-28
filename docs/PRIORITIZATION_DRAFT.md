# Prioritization & AI-Readiness Framework

This framework balances features, bugs, and tech debt by focusing on **Definition of Ready** and **Agent Autonomy**. It ensures that tasks are not just "important," but actually prepared for an AI agent to execute.

## 1. Categorization (The "What")
Every issue must have exactly one of these labels:
*   `type: feature`: Net-new capabilities or enhancements.
*   `type: bug`: Something is broken or behaving unexpectedly.
*   `type: tech-debt`: Refactoring, updating dependencies, improving test coverage, or maintaining architecture.

## 2. Readiness Labels (The "Gate")
Before an issue is assigned to an agent, its readiness must be assessed.
*   `ready: yes`: Issue meets the **Definition of Ready** (see below) and is ready for handoff.
*   `ready: blocked`: Issue is understood but blocked by a missing dependency, access, decision, or external condition.
*   `ready: needs-spec`: Issue requires a written spec, plan, or acceptance criteria before it can be coded.

### Definition of Ready (DoR)
An issue is `ready: yes` ONLY when it contains:
- **Outcome**: Clear description of the desired end state.
- **Context**: Known repository and file paths.
- **Criteria**: Explicit acceptance criteria (what does "done" look like?).
- **Verification**: A specific test or shell command to verify the change.
- **Safety**: Rollback or safety notes for risky changes (e.g., live services, migrations).
- **Simplicity**: Small enough scope for a single coding pass.
- **Clarity**: No unresolved product or design questions.

## 3. Agent Autonomy / Execution (The "How")
Defines how much human intervention is required for an AI agent to complete the task.
*   `agent: autonomous`: Clear, bounded, and testable. Agent can implement with minimal input.
*   `agent: needs-input`: Mostly clear, but requires 1-2 specific user decisions to proceed.
*   `agent: needs-plan`: Multi-file, architectural, or risky. Requires a written plan/spec (e.g., via Plan Mode) before any code is written.
*   `agent: discuss-first`: Ambiguous product direction, UX tradeoffs, security implications, or data model changes. Requires active discussion.

## 4. Primary Sort Order (Hierarchy)
When planning or sorting the backlog, follow this hierarchy:
1.  **Priority**: `now` > `next` > `later`
2.  **Readiness**: `ready: yes` > `ready: blocked` > `ready: needs-spec`
3.  **Autonomy**: `autonomous` > `needs-input` > `needs-plan` > `discuss-first`
4.  **Scope** (Secondary): `size: S` (<2h), `size: M` (Half-day), `size: L` (1-2 days). Use only for capacity context.

## 5. Bug Severity (Urgency)
Bugs are prioritized based on impact, independent of readiness.
*   `bug: P0 (Critical)`: System down, data loss. **Drop everything and fix now.**
*   `bug: P1 (High)`: Major feature broken, no easy workaround. Fix in the current batch (`now`).
*   `bug: P2 (Normal)`: Annoyance or edge-case failure with a workaround. Schedule for `next`.
*   `bug: P3 (Low)`: Cosmetic issue or very rare edge case. Schedule for `later`.

## 6. The Allocation Strategy (Balancing the Diet)
To ensure technical health, maintain a balanced mix in the `now` queue:
*   **The 60/20/20 Rule**: Target 60% Features, 20% Bugs, 20% Tech Debt.
*   **The "Tax" Method**: For every `size: L` feature, you must resolve one `size: S/M` tech debt item.

## 7. Examples

| Scenario | Labels |
| :--- | :--- |
| **Small bug, ready to go** | `type: bug`, `bug: P1`, `ready: yes`, `agent: autonomous`, `size: S` |
| **Feature needing one decision** | `type: feature`, `ready: blocked`, `agent: needs-input`, `size: M` |
| **Major refactor/migration** | `type: tech-debt`, `ready: needs-spec`, `agent: needs-plan`, `size: L` |
| **New product concept** | `type: feature`, `ready: blocked`, `agent: discuss-first` |

## Next Steps for Implementation
1.  **Documentation**: Update `AGENTS.md` and `BACKLOG.md` with these rules.
2.  **GitHub Labels**: Create these standardized labels across all repositories.
3.  **Project Sync**: Update GitHub Actions (e.g., `sync-project-priority.yml`) to map these labels to the Project Board.
