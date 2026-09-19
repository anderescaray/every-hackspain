/** @type {import('next').NextConfig} */
const nextConfig = {
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  // Keep AGENTS.md generation available for the team without polluting commits.
  // agentRules defaults to true in this Next version.
};

export default nextConfig;
