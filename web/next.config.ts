import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Reader pages query Neon on every request; Cache Components conflicts with force-dynamic.
  cacheComponents: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
