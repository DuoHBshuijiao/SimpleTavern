---
name: impeccable-frontend-iteration
description: Runs systematic frontend design-improvement loops for SimpleTavern using Impeccable, `npx impeccable detect`, scoped audits, and iterative fixes. Use when improving UI aesthetics, glass hierarchy, animation consistency, visual polish, or frontend UX details across the large Vue codebase.
---

# Impeccable Frontend Iteration

Use this skill for SimpleTavern frontend design work that needs global judgment, not one-off spacing tweaks. The app is a product UI with a mature, restrained, multi-layer glass theme. Preserve that identity.

## Required Setup

Before changing UI:

1. Run Impeccable context for the relevant target:
   ```bash
   node .claude/skills/impeccable/scripts/context.mjs --target frontend/src
   ```
   If the project-local script is not present, use the installed Impeccable context script from the user's Claude skills directory and keep the same `--target`.
2. Read `PRODUCT.md`.
3. Read `DESIGN.md` if it exists. If it does not, infer current identity from:
   - `frontend/src/styles/variables.css`,
   - `frontend/src/styles/components/*.css`,
   - representative components in the target area.
4. Treat this as product UI. Load and follow Impeccable's product-register guidance when available.

## Scope First

Never start by asking Impeccable to critique the whole `frontend/src` and blindly applying the output. The frontend is large; determine a scope first.

Good scopes:

- one workflow: settings, import/export, TTS, MVU, WebGPU, HTTP Log,
- one layer family: modals, drawers, popovers, buttons, inputs,
- one route/page: `ChatPage.vue` plus its direct child components,
- one defect class: contrast, motion, hierarchy, hover/active states, overflow.

Create a scope matrix:

```markdown
| Area | Files | User-facing risk | Existing pattern | Planned treatment |
|---|---|---|---|---|
```

## Detection

Run local Impeccable detection on scoped paths:

```bash
npx impeccable detect frontend/src/components/SettingsDrawer.vue
npx impeccable detect frontend/src/components/modals
npx impeccable detect frontend/src/views/ChatPage.vue
```

Use relative paths from the repository root. If `npx impeccable detect` is unavailable, use the installed detector script if present, or fall back to targeted `rg` scans and state that fallback.

Detection findings are signals, not orders. Before implementing a suggestion, ask:

- Does this apply to all related components, not just one instance?
- Would applying it globally improve consistency?
- Does it preserve SimpleTavern's glass hierarchy and restrained product identity?
- Does it improve readability, focus, or workflow clarity?
- Does it conflict with existing tokens, accessibility, or performance?

Partially adopt findings when that is the coherent system choice.

## SimpleTavern Visual Rules

- No visual background gradients, except the MVU state bar scan band in `StateVariablesBar.vue`.
- Use translucent solid color surfaces, blur, border, and shadow to express hierarchy.
- Preserve the L0-L6 glass depth ladder in `variables.css` and `utilities.css`.
- Left sidebar keeps the sandwich structure: dark top/bottom, lighter character list middle.
- Settings drawer stays deep/dark; inner panels, inline sheets, modals, and popovers get progressively brighter and stronger.
- Popovers/dropdowns should escape clipping and use popover-level surface tokens.
- Main text and controls must remain readable; glass effects never outrank contrast.
- Motion must be 150-250ms, purposeful, and respect `prefers-reduced-motion`.

## Implementation Loop

1. **Read target files**  
   Include styles, component templates, and nearby shared primitives.

2. **Run detection and static searches**  
   Useful searches:
   - `linear-gradient|radial-gradient|bg-gradient`
   - `bg-white/|bg-black/|bg-slate-|bg-zinc-|rgba(`
   - `backdrop-blur-sm|backdrop-blur-md|backdrop-blur-xl`
   - `modal-surface|drawer-surface|glass-l`
   - `aria-label|role="dialog"|aria-modal`

3. **Design the system-level fix**  
   Do not fix one `1rem` gap unless the same rhythm should exist across that component family. Prefer tokens and shared classes over isolated local values.

4. **Edit narrowly but consistently**  
   Use existing tokens and components. Add tokens only when the repeated pattern needs a name.

5. **Re-scan for omissions**  
   After edits, rerun the relevant `npx impeccable detect <relative path>` and targeted searches. Look for sibling components that now diverge.

6. **Verify**  
   Do **not** add or run pytest / Vitest / Playwright. At minimum:
   ```bash
   cd frontend && npm run build
   ```
   If visible controls changed, update `docs/specs/FRONTEND-FEATURES.md`.

7. **Report design distance**  
   Tell the user what became more coherent, what remains, and whether the remaining work belongs to the current version or a later structural refactor.

## Common Workstreams

### Polish A Component Family

1. Inventory every instance of the family.
2. Pick the canonical token/class.
3. Migrate siblings.
4. Verify hover, focus, active, disabled, loading, empty, and error states.

### Improve Motion

1. Inventory transitions and animations.
2. Remove decorative motion.
3. Standardize easing and durations.
4. Add reduced-motion fallback.
5. Confirm no content depends on an animation to appear.

### Improve Glass Hierarchy

1. Map each surface to L0-L6.
2. Check that deeper surfaces are clearer, not merely blurrier.
3. Ensure dropdowns and popovers are not clipped by parent overflow.
4. Verify contrast on text and controls.

## Output Format

```markdown
## Scope
...

## Design Decisions
...

## Changes
...

## Verification
...

## Remaining Work
...
```

Include manual Chinese commit commands. Do not auto-commit.
