/**
 * Production build = static export (frontend/out), served by FastAPI on the
 * same origin as the API. In `next dev`, /api is proxied to the backend.
 */
const isDev = process.env.NODE_ENV !== "production";
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = isDev
  ? {
      async rewrites() {
        return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
      },
    }
  : {
      output: "export",
      trailingSlash: true,
      images: { unoptimized: true },
    };

export default nextConfig;
