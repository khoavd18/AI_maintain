import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The current UI does not use optimized local or remote images. Disabling the
  // optimizer removes the runtime Sharp endpoint while the framework-owned
  // Sharp advisory is awaiting a compatible stable Next.js release.
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
