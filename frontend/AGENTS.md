# Frontend verification and integration

- Run commands from `frontend/`: `npm ci`, `npm run build`, `npm run lint`, `npm run typecheck`, `npm test`.
- Browser verification: `npx playwright install chromium`, then `npm run build` and `npm run test:e2e`. Playwright starts the production app on port 3106 and covers desktop/mobile interactions and automated WCAG checks. Reports and screenshots are ignored by git.
- Local preview: `npm run dev -- --port 3107`, then `/companies/COMP_0356`, `/companies/COMP_0655`, or `/companies/COMP_1171`. The root Portfolio route and global navigation are intentionally not implemented here.
- UI entry point: `components/insights/CompanyInsights.tsx`. Styles are scoped in `components/insights/insights.module.css`; the root layout is only a minimal standalone host for integration with the Portfolio shell.
- The route reads only `getCompanyDetail(companyId)` from `services/companyData.ts`. Unknown IDs return null and render a not-found state. Replace the adapter, not UI imports, when precomputed data is available.
- `types/companyDetail.ts` is the versioned payload contract. Scores/confidence are 0–100; null confidence means unavailable; dates are ISO calendar dates; amounts are EUR units (not cents); simulation input values are deltas, not absolute terms.
- Cash Truth gross amounts include both circulation legs. Gross movement and identified net amounts are different bases. Unknown attribution must stay null, never become zero operating cash. Evidence samples are explicitly not a complete reconciliation.
- Time Borrowed clocks are independently supplied cohort medians and need not add up. AR is time granted; AP is time received. Additional AP late payment must not be marked as an improvement.
- What-if uses fixed illustrative sensitivities, rounds/caps Pulse to 0–100, never mutates the company snapshot, and must retain the statement `Scenario, not forecast.`.
- This frontend has no API routes, uploads, authentication, financial processing, or backend dependencies. Avoid loading external fonts or services for the offline mock demo.
- Next 16.3.4 is pinned because the initially considered Next 15.5.25 depends on a vulnerable PostCSS version; audit dependencies before changing the framework version.
