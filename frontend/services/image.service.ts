import { API_BASE, apiFetch } from '@/lib/api-client';
import { getAccessToken } from '@/lib/auth-storage';
import type { GenerationRequest, ProviderName } from '@/types/api';

export function generateImages(
  prompt: string,
  providers: ProviderName[],
  uploadFileId?: string,
): Promise<GenerationRequest> {
  return apiFetch<GenerationRequest>('/images/generate', {
    method: 'POST',
    // A retry of the same click must not double-charge credits.
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: { prompt, providers, upload_file_id: uploadFileId ?? null },
  });
}

export function generateWithUpload(
  file: File,
  prompt: string,
  providers: ProviderName[],
): Promise<GenerationRequest> {
  const form = new FormData();
  form.append('file', file);
  form.append('prompt', prompt);
  form.append('providers', providers.join(','));
  return apiFetch<GenerationRequest>('/images/generate-with-upload', { method: 'POST', body: form });
}

export function listGenerations(limit = 20, offset = 0): Promise<GenerationRequest[]> {
  return apiFetch<GenerationRequest[]>(`/images?limit=${limit}&offset=${offset}`);
}

export function getGeneration(id: string): Promise<GenerationRequest> {
  return apiFetch<GenerationRequest>(`/images/${id}`);
}

export function regenerate(id: string, provider?: ProviderName): Promise<GenerationRequest> {
  return apiFetch<GenerationRequest>(`/images/${id}/regenerate`, {
    method: 'POST',
    body: { provider: provider ?? null },
  });
}

/** Downloads an authenticated image to the user's device. */
export async function downloadImage(imageUrl: string, filename: string): Promise<void> {
  const token = getAccessToken();
  const res = await fetch(`${API_BASE}${imageUrl.replace(/^\/api\/v1/, '')}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!res.ok) throw new Error('Could not download this image.');

  const blobUrl = URL.createObjectURL(await res.blob());
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(blobUrl);
}
