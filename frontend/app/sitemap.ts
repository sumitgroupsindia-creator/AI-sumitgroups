import type { MetadataRoute } from 'next';

const BASE_URL = 'https://ai.sumitgroups.com';

export default function sitemap(): MetadataRoute.Sitemap {
  // Only public marketing pages: everything else is behind authentication.
  return [
    { url: BASE_URL, lastModified: new Date(), changeFrequency: 'weekly', priority: 1 },
    { url: `${BASE_URL}/pricing`, lastModified: new Date(), changeFrequency: 'monthly', priority: 0.8 },
  ];
}
