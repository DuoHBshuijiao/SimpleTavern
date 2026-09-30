---
name: roadmap-iteration
description: Drives roadmap-following improvement loops for SimpleTavern. Use when the user asks to continue a version plan, follow docs/ roadmap or backlog, raise completion percentage, improve coverage, update handoff docs, or compare actual progress with initial requirements.
---

# Roadmap Iteration

Use this skill to advance SimpleTavern by following `docs/` rather than ad hoc prompts. The workflow must preserve the repository's rule: do not auto-commit; generate Chinese commit commands for the user.

## Context To Read First

Read, in this order:

1. `docs/00-INDEX.md` if present.
2. `docs/01-ROADMAP.md`.
3. `docs/02-BACKLOG.md`.
4. `docs/state/CURRENT.md`.
5. `docs/state/LAST_HANDOFF.md`.
6. `CHANGELOG.md`.
7. The original user requirements in the current conversation.

Then inspect the relevant code areas before deciding scope. Do not infer APIs or file responsibilities without reading them.

## Operating Loop

1. **Establish target**  
   State the target version/task, current claimed completion, and the evidence you will use. If docs say "done", verify against code and `docs/specs/` before accepting it.

2. **Delegate scope discovery**  
   Use readonly subagents for broad scans when the task touches many files. Ask them to return:
   - affected UI/backend/doc areas,
   - gaps against initial requirements,
   - high-risk files,
   - suggested verification commands.

3. **Plan coverage**  
   Convert the scan into a file/area matrix. Cover main paths first, then low-frequency modals and edge flows. Avoid changing unrelated behavior.

4. **Implement in bounded batches**  
   Each batch should have one clear theme, for example:
   - design-system foundation,
   - high-frequency chat path,
   - settings and configuration,
   - modal/a11y unification,
   - backend fast-fail and spec updates,
   - docs/version/handoff.

5. **Review for omissions**  
   After each batch, run a second readonly review or targeted searches for missed patterns. Treat "same UI family but not migrated" as a coverage gap.

6. **Verify**  
   Do **not** add or run pytest / Vitest / Playwright. After substantive work:
   - `cd frontend && npm run build`
   - 对照 `docs/specs/BACKEND-API.md` 与 `docs/specs/FRONTEND-FEATURES.md`
   - 若改了接口或可见控件，先更新规格文档

7. **Update docs**  
   Keep docs honest. Update roadmap/backlog/current/handoff/changelog only to match real completed work. Do not mark 100% if known gaps remain.

8. **Report progress distance**  
   Tell the user:
   - what improved,
   - what evidence supports it,
   - approximate completion percentage,
   - remaining blockers to the next milestone,
   - manual Chinese commit commands.

## Completion Judgment

Score progress conservatively:

- 50-65%: docs or foundation exist, but major code paths are not migrated.
- 70-85%: main paths match `docs/specs/`, but low-frequency surfaces or audit gaps remain.
- 90%+: broad UI/backend/doc coverage is real, major static scans are clean, and remaining work is structural or future-version work.
- 100%: only when initial requirements, docs, code, specs, and review scans all agree.

## Guardrails

- Never auto-commit.
- Never rewrite user changes that are unrelated to the batch.
- Prefer existing APIs, stores, composables, and tokens.
- If a requirement conflicts with `docs/`, call it out and ask or state the chosen precedence.
- For UI work, pair static scans with `npm run build` and spec-doc updates. Never reintroduce automated tests.

## Final Response Template

```markdown
完成到约 X%。

本轮推进：
- ...

验证：
- ...

剩余：
- ...

手动提交：
git add ...
git commit -m "中文提交信息"
```
