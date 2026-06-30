# Product

## Register

product

## Users

SimpleTavern is for a single local user running AI roleplay on a trusted personal machine. The user is configuring models, characters, chats, world books, MVU state, knowledge graph, imports, exports, TTS, and visual background behavior while staying inside one dense app shell.

## Product Purpose

SimpleTavern provides a local, JSON-backed AI roleplay workspace that is easy to launch, inspect, migrate, and repair without a traditional database. Success means the app feels coherent and dependable across long sessions: configuration is discoverable, chat workflows stay smooth, data is transparent, and errors are explicit enough to fix.

## Brand Personality

Mature, immersive, restrained.

The interface should feel like a polished local tool with a layered glass material system: atmospheric enough for roleplay, but still calm and legible enough for heavy settings, debugging, and data maintenance.

## Anti-references

- Generic SaaS dashboards with bright gradient cards, decorative glow, and inconsistent button vocabularies.
- Overly playful chat apps that sacrifice dense configuration clarity.
- Terminal-only developer tools that feel hostile to non-developer maintenance tasks.
- Glassmorphism used as decoration without readability, hierarchy, or performance discipline.

## Design Principles

1. Mature glass hierarchy: use translucent solid surfaces, blur, borders, and shadow to express depth; each deeper interaction layer should become clearer and more legible.
2. Workflow trust over spectacle: visual polish should reduce uncertainty in chat, import/export, MVU, TTS, WebGPU, and settings workflows.
3. Explicit local control: dangerous actions, persistence, imports, and backend failures should be visible, reversible where possible, and never silently hidden.
4. Consistency beats novelty: buttons, inputs, drawers, modals, popovers, and confirmation patterns should behave the same across the app.
5. Progressive complexity: advanced configuration can be dense, but it should be grouped, staged, and previewable before committing.

## Accessibility & Inclusion

Target WCAG AA contrast for text and controls. Respect `prefers-reduced-motion`; animations should communicate state changes rather than decorate. Preserve keyboard access for dialogs, drawers, popovers, and major settings workflows. Prioritize readable text over glass effects whenever the two conflict. Do not rely on the native `title` attribute to name or describe controls, since it is not reliably exposed to keyboard or assistive technology; use `aria-label` (or visible text / `aria-labelledby`) for accessible names instead.
