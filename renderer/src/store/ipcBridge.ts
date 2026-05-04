// Thin wrapper around window.boxccAPI to keep type narrowing local.
import type { BoxccApi } from '@/types/boxccApi';

export function api(): BoxccApi {
  if (!window.boxccAPI) {
    throw new Error('boxccAPI not available — preload not loaded?');
  }
  return window.boxccAPI;
}
