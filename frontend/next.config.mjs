/** @type {import('next').NextConfig} */
let rawBackendUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

rawBackendUrl = rawBackendUrl.trim().replace(/\/+$/, "");

// Ensure protocol is present so Next.js rewrites destination is a valid URL
const backendUrl =
  rawBackendUrl.startsWith("http://") || rawBackendUrl.startsWith("https://")
    ? rawBackendUrl
    : `https://${rawBackendUrl}`;

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
