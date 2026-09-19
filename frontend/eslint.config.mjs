import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const config = [
  ...coreWebVitals,
  ...typescript,
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "next-env.d.ts",
      "playwright-report/**",
      "test-results/**",
      // Node test stub: must use require() to register .css module extension
      "tests/support/cssModules.cjs",
    ],
  },
];

export default config;
