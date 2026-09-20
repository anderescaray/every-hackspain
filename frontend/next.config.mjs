/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Las páginas son `force-dynamic` y leen los análisis del disco con `fs` en runtime. Esas rutas
  // se construyen en tiempo de ejecución, así que el rastreo automático no las ve y en un
  // despliegue serverless (Vercel) los ficheros no entrarían en el bundle de la función.
  outputFileTracingIncludes: {
    "/": ["./public/generated/portfolio.json"],
    "/companies/[id]": ["./public/generated/companies/*.json"],
    "/groups/[id]": ["./public/generated/groups/*.json", "./public/generated/companies/*.json"],
    "/groups/[id]/network": ["./public/generated/groups/*.json", "./public/generated/companies/*.json"],
    "/groups/[id]/recommendations": ["./public/generated/groups/*.json", "./public/generated/companies/*.json"],
  },
  // Keep AGENTS.md generation available for the team without polluting commits.
  // agentRules defaults to true in this Next version.
};

export default nextConfig;
