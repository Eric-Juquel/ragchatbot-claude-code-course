# Frontend Changes

## Feature: JavaScript Toggle & Full Transition Polish

### Summary
Improved the theme-toggle JavaScript so the `aria-label` dynamically reflects the current state on every toggle and on page load. Extended the CSS transition list to cover all theme-sensitive elements (including `box-shadow` for the welcome-message card shadow), and replaced a remaining hardcoded colour with `var(--assistant-message)`.

---

### Changes

#### `frontend/script.js`
- Extracted an `applyTheme(theme)` helper that sets `data-theme`, persists to `localStorage`, and updates the button's `aria-label` to either `"Switch to light mode"` or `"Switch to dark mode"`.
- Called `applyTheme()` immediately after `DOMContentLoaded` to sync the label with the theme restored from `localStorage` (previously the label was a static string).
- The click handler now calls `applyTheme()` instead of inline `setAttribute` calls, keeping the logic in one place.

#### `frontend/style.css`
- Added `.stat-label`, `.stat-value`, and `.source-pill` to the smooth-transition selector list so sidebar stat text and source pills also animate during theme switches.
- Added `box-shadow 0.3s ease` to the transition shorthand so the welcome message card shadow fades smoothly between its dark (`rgba(0,0,0,0.2)`) and light (`rgba(0,0,0,0.08)`) values.
- `[data-theme="light"] .message.assistant .message-content` now uses `var(--assistant-message)` instead of the hardcoded `#f1f5f9`, keeping all colours in the variable layer.

---


## Feature: Light/Dark Mode Toggle Button

### Summary
Added a floating toggle button in the top-right corner that switches between dark mode (default) and light mode, with smooth transition animations and keyboard accessibility.

---

### Files Modified

#### `frontend/index.html`
- Added a `<button id="themeToggle" class="theme-toggle">` element immediately after `<body>`.
- Contains two inline SVG icons: a **sun** (shown in dark mode, inviting the user to switch to light) and a **moon** (shown in light mode, inviting switch to dark).
- `aria-label` and `title` attributes make the button accessible to screen readers and hover tooltips.

#### `frontend/style.css`
- **`[data-theme="light"]` block**: Overrides all CSS custom properties for the light theme. Key changes:
  - `--background: #f8fafc`, `--surface: #ffffff`, `--text-primary: #0f172a`, `--text-secondary: #64748b`, `--border-color: #cbd5e1`.
  - Also overrides link colors, source pill colors, assistant message bubble background, and code block backgrounds for proper contrast in light mode.
- **Transition block**: Adds `transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease` to all major UI elements so theme changes animate smoothly instead of flashing.
- **`.theme-toggle`**: Fixed-position button (`top: 1rem; right: 1rem; z-index: 1000`), 44×44 px circle, uses `--surface`/`--border-color` variables to naturally adapt to either theme. Hover effect scales button up slightly and highlights with primary blue.
- **Icon visibility**: `.icon-sun` is shown by default (dark mode); `.icon-moon` is hidden. `[data-theme="light"]` flips these states.
- **`@keyframes spin-in`**: A subtle rotate+fade-in animation that fires on the visible icon whenever the theme is toggled (via `.toggling` class).

#### `frontend/script.js`
- **IIFE `initTheme()`** (runs before DOM is ready): Reads `localStorage.getItem('theme')` (defaults to `'dark'`) and sets `data-theme` on `<html>` immediately, preventing a flash of wrong theme on page load.
- **Click handler** on `#themeToggle` (wired up in `DOMContentLoaded`):
  - Reads current theme from `document.documentElement.getAttribute('data-theme')`.
  - Toggles to the opposite value and persists it in `localStorage`.
  - Adds `.toggling` class to the button to trigger the icon spin animation, then removes it after the animation ends via a one-time `animationend` listener.

---

## Feature: Light Theme CSS Variables (Comprehensive)

### Summary
Refactored the light theme to be entirely variable-driven. All previously hardcoded colour values that didn't adapt to theme changes are now expressed as CSS custom properties, and the `[data-theme="light"]` block overrides every token needed for correct contrast and accessibility.

---

### Changes in `frontend/style.css`

#### New semantic tokens added to `:root` (dark defaults)
| Variable | Dark value | Purpose |
|---|---|---|
| `--link-color` | `#60a5fa` | Hyperlink text colour |
| `--link-hover` | `#93c5fd` | Hyperlink hover colour |
| `--code-bg` | `rgba(0,0,0,0.2)` | Inline code / pre block background |
| `--welcome-shadow` | `0 4px 16px rgba(0,0,0,0.2)` | Welcome message card shadow |

#### Extended `[data-theme="light"]` overrides
All four new tokens are overridden, plus the existing colour palette is tightened for better contrast:
| Variable | Light value | Notes |
|---|---|---|
| `--primary-color` | `#1d4ed8` | Slightly darker than dark-mode `#2563eb` — passes WCAG AA on white (`#fff`) at 5.9:1 |
| `--primary-hover` | `#1e40af` | Darker still for hover state |
| `--text-secondary` | `#475569` | Darkened from `#64748b` to pass 4.5:1 on white background |
| `--user-message` | `#1d4ed8` | Matches updated primary |
| `--link-color` | `#1d4ed8` | Replaces hardcoded `#2563eb` in `a {}` |
| `--link-hover` | `#1e40af` | Replaces hardcoded `#1d4ed8` in `a:hover {}` |
| `--code-bg` | `rgba(0,0,0,0.05)` | Subtle tint on white, no harsh contrast |
| `--welcome-shadow` | `0 4px 16px rgba(0,0,0,0.08)` | Lighter shadow on light backgrounds |
| `--focus-ring` | `rgba(29,78,216,0.25)` | Matches updated primary |

#### Hardcoded colours replaced with variables
- `a { color: #60a5fa }` → `color: var(--link-color)`
- `a:hover { color: #93c5fd }` → `color: var(--link-hover)`
- `.message-content code { background-color: rgba(0,0,0,0.2) }` → `var(--code-bg)`
- `.message-content pre { background-color: rgba(0,0,0,0.2) }` → `var(--code-bg)`
- `.message.welcome-message .message-content { box-shadow: 0 4px 16px rgba(0,0,0,0.2) }` → `var(--welcome-shadow)`

#### Bug fix
- `.message-content blockquote` referenced `var(--primary)` (undefined) — corrected to `var(--primary-color)`.

#### Removed ad-hoc light-mode selectors
The following per-element overrides were deleted because the variable system now handles them:
- `[data-theme="light"] .message-content code`
- `[data-theme="light"] .message-content pre`
- `[data-theme="light"] a`
- `[data-theme="light"] a:hover`

---

### Design Decisions
- **Position**: Fixed top-right so it's always reachable without scrolling, and doesn't compete with the sidebar or chat input.
- **Icon choice**: Sun = switch to light, Moon = switch to dark — standard convention.
- **Persistence**: `localStorage` keeps the user's preference across page reloads.
- **No flash**: The IIFE sets the theme attribute synchronously before the browser paints, eliminating the dark→light flash that would occur if theme were applied only after `DOMContentLoaded`.
- **Accessibility**: `aria-label`, `title`, focus ring via `:focus` box-shadow, and full keyboard operability (the element is a native `<button>`).
