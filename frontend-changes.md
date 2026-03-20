# Frontend Changes

## Code Quality Tooling Added

### New Files

| File | Purpose |
|------|---------|
| `frontend/package.json` | npm project definition with quality tool scripts |
| `frontend/.prettierrc` | Prettier configuration (formatting rules) |
| `frontend/.eslintrc.js` | ESLint configuration (JS linting rules) |
| `frontend/.prettierignore` | Excludes `node_modules/` from formatting |
| `frontend/scripts/check.sh` | Shell script to run all quality checks |

### Tools Configured

**Prettier** (equivalent of Black for JS/HTML/CSS)
- Print width: 100 characters
- 2-space indentation
- Single quotes for JS strings
- Trailing commas in ES5 positions
- LF line endings

**ESLint**
- Extends `eslint:recommended`
- `no-var` enforced (use `const`/`let`)
- `prefer-const` enforced
- `no-console` warned
- Browser globals + `marked` (CDN) declared

### npm Scripts

```bash
npm run format        # Auto-format all JS/HTML/CSS files
npm run format:check  # Check formatting without modifying files
npm run lint          # Lint script.js
npm run lint:fix      # Auto-fix lint issues in script.js
npm run check         # Run format:check + lint (CI-ready)
```

### Dev Script

```bash
./frontend/scripts/check.sh   # Runs all quality checks with clear output
```

Auto-installs dependencies if `node_modules/` is missing.

### Formatting Fixes Applied to Existing Code

**script.js**
- Converted 4-space indentation to 2-space (Prettier standard)
- Removed double blank lines between function declarations
- Removed trailing whitespace
- Added trailing commas in object/array literals
- Normalized arrow function parentheses (`(button) =>` instead of `button =>`)
- Reformatted long `addMessage()` call with proper line breaks

**style.css**
- Simplified `padding: 0.25rem 0.5rem 0.25rem 0.5rem` → `padding: 0.25rem 0.5rem`

**index.html**
- Removed extra blank line before `</body>`
- Fixed closing `</body>` indentation to match document structure
