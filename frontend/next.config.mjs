/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  async rewrites() {
    // In dev the backend runs on a separate port; in Docker the reverse proxy handles /api.
    const backend = process.env.BACKEND_INTERNAL_URL;
    return backend ? [{ source: '/api/:path*', destination: `${backend}/api/:path*` }] : [];
  },
};
export default nextConfig;
