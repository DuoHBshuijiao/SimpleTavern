---
name: SimpleTavern
description: A mature local AI roleplay workspace with restrained multi-layer glass UI.
colors:
  rose-mist-primary: "#c58aa2"
  rose-mist-primary-hover: "#d8a3b8"
  primary-action: "#9a6a7d"
  primary-action-hover: "#a9788a"
  canvas-deep: "#151217"
  surface-soft-glass: "#271f2ab8"
  surface-elevated-glass: "#271f2ae6"
  text-main: "#fcf7fa"
  text-muted: "#b5a4af"
  border-subtle: "#ffffff0d"
  border-default: "#ffffff1a"
  border-strong: "#ffffff26"
  overlay-heavy: "#000000ad"
typography:
  display:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
  title:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.25
  mono:
    fontFamily: "JetBrains Mono, Fira Code, Consolas, Monaco, Courier New, monospace"
    fontSize: "0.75rem"
rounded:
  sm: "0.375rem"
  md: "0.5rem"
  lg: "0.75rem"
  xl: "1rem"
  2xl: "1.5rem"
  3xl: "2rem"
  full: "9999px"
spacing:
  xs: "0.25rem"
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
  2xl: "3rem"
components:
  button-primary:
    backgroundColor: "{colors.primary-action}"
    textColor: "{colors.text-main}"
    rounded: "{rounded.lg}"
    padding: "0.5rem 1rem"
    height: "2.25rem"
  button-primary-hover:
    backgroundColor: "{colors.primary-action-hover}"
    textColor: "{colors.text-main}"
    rounded: "{rounded.lg}"
  modal-surface:
    backgroundColor: "{colors.surface-elevated-glass}"
    textColor: "{colors.text-main}"
    rounded: "{rounded.2xl}"
    padding: "1.5rem"
  input:
    backgroundColor: "{colors.surface-soft-glass}"
    textColor: "{colors.text-main}"
    rounded: "{rounded.lg}"
    padding: "0.5rem 0.75rem"
---

# Design System: SimpleTavern

## 1. Overview

**Creative North Star: "Quiet Roleplay Cockpit"**

SimpleTavern is a dense local product surface for long AI roleplay sessions, not a decorative landing page. Its visual system should feel like a quiet cockpit: many controls, panels, logs, and states are available, but the interface stays calm, layered, and legible.

The design language is mature multi-layer glass. Depth is conveyed with translucent solid surfaces, blur, borders, and shadow rather than gradients or decorative glow. The system rejects generic SaaS dashboards, overly playful chat skins, hostile terminal-only density, and glass effects that reduce readability.

**Key Characteristics:**

- Restrained dark product UI with one theme accent at a time.
- Layered glass depth from page canvas to popover, with clearer and brighter surfaces as interaction depth increases.
- Compact but readable controls for settings-heavy workflows.
- Familiar product interaction patterns: buttons, fields, drawers, modals, popovers, and confirmations behave consistently.

## 2. Colors

The palette is a restrained dark glass system with theme-driven accents. The default character is Rose Mist: muted rose interaction color over a deep violet-black canvas.

### Primary

- **Rose Mist Primary** (`rose-mist-primary`): the default accent for primary actions, current selections, focus hints, and key state indicators.
- **Rose Mist Action** (`primary-action`): the darker action version used by primary buttons so white text stays readable and hover never becomes piercing.

### Neutral

- **Canvas Deep** (`canvas-deep`): the app background and deepest page layer.
- **Soft Glass Surface** (`surface-soft-glass`): the middle layer for chrome, sidebars, and contained panels.
- **Elevated Glass Surface** (`surface-elevated-glass`): the clearer top layer for modals and committed interaction surfaces.
- **Text Main** (`text-main`): primary text on all glass surfaces.
- **Text Muted** (`text-muted`): secondary labels and hints. Use carefully; body copy must remain readable.
- **Glass Borders** (`border-subtle`, `border-default`, `border-strong`): edges, dividers, focus-adjacent structure, and popover separation.

### Named Rules

**The No Gradient Background Rule.** Visual backgrounds must be translucent solid color. The only allowed gradient is the MVU state bar scanning animation.

**The Accent Rarity Rule.** The current theme accent is for primary actions, selection, and state. It is not decoration.

**The Readability Beats Glass Rule.** If a glass layer makes text harder to read, make the surface more solid or the text stronger before adding more blur.

## 3. Typography

**Display Font:** Inter, system-ui, Segoe UI, Roboto, sans-serif  
**Body Font:** Inter, system-ui, Segoe UI, Roboto, sans-serif  
**Label/Mono Font:** JetBrains Mono, Fira Code, Consolas, Monaco, Courier New, monospace

**Character:** A single practical sans family carries the product UI. Typography is compact and utilitarian, with hierarchy coming from weight, size, spacing, and grouping rather than display flourishes.

### Hierarchy

- **Display** (600, 1.5rem, 1.2): rare page or modal titles.
- **Title** (600, 1.125rem, 1.35): panel headings, drawer titles, modal headings.
- **Body** (400, 0.875rem, 1.5): settings copy, labels with supporting text, list metadata.
- **Label** (500, 0.75rem, 1.25): compact controls, chips, captions, status labels.
- **Mono** (0.75rem): IDs, model names, code, HTTP details, shader/source snippets.

### Named Rules

**The Product Sans Rule.** Do not introduce display fonts into labels, buttons, data, settings, or logs.

**The Dense But Legible Rule.** Compact UI is allowed, but placeholder text, hints, and secondary text must still be readable on the actual glass surface behind them.

## 4. Elevation

SimpleTavern uses tonal glass layering as the primary elevation model. Shadows support depth, but the core hierarchy is the L0-L6 sequence: canvas, layout rail, chat chrome, chrome widget, dock/settings, modal, popover. Deeper interaction layers become clearer, brighter, and more separated.

### Shadow Vocabulary

- **Glass Soft** (`--shadow-glass-l2`): low lift for cards and subtle surfaces.
- **Glass Panel** (`--shadow-glass-l4`): dock panels, drawers, and major floating regions.
- **Glass Modal** (`--shadow-glass-l5`): committed modal surfaces.
- **Glass Popover** (`--shadow-glass-l6`): dropdowns, popovers, and confirmation surfaces.

### Named Rules

**The Depth Ladder Rule.** Never choose surface color by eye alone. Map the surface to L0-L6 first, then use the matching token.

**The Nested Blur Rule.** Do not stack strong blur decoratively. If a child surface is deeper, make it clearer and more solid, not merely blurrier.

## 5. Components

### Buttons

- **Shape:** gently curved rectangles (0.75rem radius) with compact height (2.25rem minimum).
- **Primary:** darker theme action color with white text, subtle brand shadow, and a controlled hover state that stays below the raw bright accent.
- **Hover / Focus:** hover shifts color and may lift by 1px; focus uses `--color-focus-ring`.
- **Secondary / Ghost / Danger:** secondary uses glass neutral surfaces, ghost uses transparent-to-muted transitions, danger uses semantic error background and text.

### Chips

- **Style:** compact rounded capsules with translucent token backgrounds, token borders, and restrained accent use.
- **State:** selected chips use accent-tinted backgrounds; unselected chips remain neutral and readable.

### Cards / Containers

- **Corner Style:** large rounded glass rectangles (1rem to 1.5rem).
- **Background:** map to the L0-L6 glass ladder; do not invent one-off tinted panes.
- **Shadow Strategy:** use the elevation vocabulary above.
- **Border:** translucent border tokens define edges; never side-stripe a card.
- **Internal Padding:** 0.75rem to 1.5rem depending on density and depth.

### Inputs / Fields

- **Style:** translucent surface, 0.75rem radius, token border, compact vertical rhythm.
- **Focus:** border and focus ring shift to theme accent.
- **Error / Disabled:** semantic state colors and opacity, never invisible controls.

### Navigation

- **Style:** app-shell navigation uses the same glass ladder as the rest of the app. Left sidebar keeps a dark/light/dark sandwich structure; settings drawer stays darker with progressively brighter inner panels.

### Modals, Drawers, and Popovers

- **Modal:** L5 glass surface with strong border, modal shadow, and modal blur.
- **Drawer:** settings/dock surface with panel blur and clear border separation.
- **Popover / Dropdown:** L6 glass surface; must not be clipped by parent overflow. Prefer teleport/fixed positioning where needed.

## 6. Do's and Don'ts

### Do:

- **Do** use translucent solid color surfaces, blur, border, and shadow to express hierarchy.
- **Do** keep every primary action, selection, focus state, and danger state tied to semantic tokens.
- **Do** preserve the mature, immersive, restrained product tone from `PRODUCT.md`.
- **Do** respect `prefers-reduced-motion`; motion should communicate state changes.
- **Do** make deep interaction layers clearer and more readable than their parent surfaces.
- **Do** give every icon-only or otherwise ambiguous control an accessible name through `aria-label` (or visible text / `aria-labelledby`).

### Don't:

- **Don't** use generic SaaS dashboards with bright gradient cards, decorative glow, and inconsistent button vocabularies.
- **Don't** make the app feel like an overly playful chat app that sacrifices dense configuration clarity.
- **Don't** turn the interface into a terminal-only developer tool that feels hostile to maintenance tasks.
- **Don't** use glassmorphism as decoration without readability, hierarchy, or performance discipline.
- **Don't** use visual background gradients, except the MVU scanning animation.
- **Don't** add colored side-stripe borders to cards, list items, callouts, or alerts.
- **Don't** use gradient text.
- **Don't** use the bare native `title` attribute as a tooltip or accessible label on controls; it is not reliably exposed to keyboard or assistive technology, so always use `aria-label` (or visible text) instead.
