/** @type {import('next').NextConfig} */
let rawBackendUrl =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

rawBackendUrl = rawBackendUrl.trim().replace(/\/+$/, "");

// Ensure protocol and domain are present so Next.js rewrites destination is valid
let backendUrl = rawBackendUrl;
if (!backendUrl.startsWith("http://") && !backendUrl.startsWith("https://")) {
  if (backendUrl.includes(".onrender.com")) {
    backendUrl = `https://${backendUrl}`;
  } else if (backendUrl.includes("localhost") || backendUrl.includes("127.0.0.1")) {
    backendUrl = `http://${backendUrl}`;
  } else {
    backendUrl = `https://${backendUrl}.onrender.com`;
  }
}

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
