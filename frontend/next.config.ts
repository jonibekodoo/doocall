import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

// CSP: strict in production; dev needs eval/inline for HMR & react-refresh.
// Presigned media (call audio, APK) lives on files.<DOMAIN_ROOT> — the
// product domain comes from env so prod (doocall.uz) and dev both work.
const ROOT = process.env.DOMAIN_ROOT || "localhost";
const PRODUCT_SRC = `https://*.${ROOT} http://*.${ROOT}`;
const CSP = [
  "default-src 'self'",
  `script-src 'self'${process.env.NODE_ENV === "development" ? " 'unsafe-eval' 'unsafe-inline'" : " 'unsafe-inline'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self' ${PRODUCT_SRC} https://*.doocall.local http://localhost:* http://127.0.0.1:*`,
  `media-src 'self' blob: ${PRODUCT_SRC} http://localhost:9000 https://*.doocall.local`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: CSP },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
  async rewrites() {
    // Dev convenience: when the app is opened on :3000 directly (Playwright,
    // local dev without nginx), proxy API calls to the backend. In prod nginx
    // owns /api/* routing and these rewrites never match.
    const target = process.env.API_PROXY_TARGET ?? "http://backend:8000";
    return [
      { source: "/api/web/:path*", destination: `${target}/api/web/:path*` },
      { source: "/api/call/:path*", destination: `${target}/api/call/:path*` },
      {
        source: "/api/public/:path*",
        destination: `${target}/api/public/:path*`,
      },
      {
        source: "/api/admin/:path*",
        destination: `${target}/api/admin/:path*`,
      },
      {
        source: "/api/partner/:path*",
        destination: `${target}/api/partner/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
