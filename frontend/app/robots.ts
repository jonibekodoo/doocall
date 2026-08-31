import type { MetadataRoute } from "next";

const BASE = process.env.NEXT_PUBLIC_SITE_URL ?? "https://doocall.local";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/cabinet/", "/api/"] }],
    sitemap: `${BASE}/sitemap.xml`,
  };
}
