# RIG Frontend

React + TypeScript + Vite + TanStack Query against the backend API. Implements
the MVP screens from [docs/14](../docs/14-ux-information-architecture.md):

- **Workbench** — ranked risk portfolio (urgency formula shown on hover),
  detail drawer with full score explanation + evidence citations, lifecycle
  transitions (dismissal requires a reason code), feedback controls.
- **Account 360** — profile facts, renewal-risk explanation with per-component
  contributions and citations, active signals (detector class + confidence
  visible), unified timeline.
- **Renewal Command Center** — renewals sorted by date, ARR due, plan-coverage
  gaps flagged.
- **Executive Brief** — generate/review/approve; claim-class badges
  (FACT / PREDICTION / AI-INTERPRETED / SUGGESTED — shape + label, never
  color alone), pending-review and excluded-claims appendices rendered
  distinctly; a blocked approval shows the verification failures verbatim.

Evidence-first conventions from docs/10 §10.4 are implemented in
`src/styles.css` + `src/components/badges.tsx`. The UI only *hides* by role —
all enforcement is server-side.

## Run

```bash
# backend (with dev sign-in enabled):
cd backend && RIG_DEV_LOGIN=1 uvicorn rig.main:app --port 8000

# frontend:
cd frontend && npm install && npm run dev   # http://localhost:5173
```

The dev sign-in screen lists seeded workspaces (`python -m rig.seed`) and
issues role-scoped tokens; it 404s unless `RIG_DEV_LOGIN=1` — production uses
SSO (WorkOS/OIDC).

Styling note: plain CSS design tokens for now; the docs/13 recommendation
(Tailwind + Radix) is a straightforward later migration — tokens map 1:1.
