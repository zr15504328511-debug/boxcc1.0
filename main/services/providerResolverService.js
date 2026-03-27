const SUPPORTED_PROVIDERS = ['OpenAI', 'Anthropic', 'Gemini', 'OpenRouter', 'Custom'];

const DEFAULT_BASE_URLS = {
  OpenAI: 'https://api.openai.com/v1',
  Anthropic: 'https://api.anthropic.com/v1',
  Gemini: 'https://generativelanguage.googleapis.com/v1beta',
  OpenRouter: 'https://openrouter.ai/api/v1',
  Custom: '',
};

function normalizeString(value) {
  return String(value || '').trim();
}

function normalizeBaseUrl(provider, baseUrl) {
  const cleaned = normalizeString(baseUrl).replace(/\/+$/, '');
  if (cleaned) {
    return cleaned;
  }
  return DEFAULT_BASE_URLS[provider] || '';
}

function validateProfile(profile = {}) {
  const errors = [];
  const provider = normalizeString(profile.provider);

  if (!normalizeString(profile.name)) {
    errors.push('Profile name is required.');
  }

  if (!provider || !SUPPORTED_PROVIDERS.includes(provider)) {
    errors.push(`Unsupported provider: ${provider || 'unknown'}.`);
  }

  if (provider === 'Custom' && !normalizeString(profile.baseUrl)) {
    errors.push('Custom provider requires a Base URL.');
  }

  return {
    ok: errors.length === 0,
    errors,
  };
}

function buildUrl(baseUrl, path) {
  return `${baseUrl.replace(/\/+$/, '')}/${path.replace(/^\/+/, '')}`;
}

function dedupe(items) {
  return Array.from(new Set(items.filter(Boolean)));
}

async function requestJson(url, headers = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers,
      signal: controller.signal,
    });

    const text = await response.text();
    let data = null;

    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = null;
    }

    if (!response.ok) {
      const detail = data?.error?.message
        || data?.message
        || (text ? text.slice(0, 240) : '')
        || `HTTP ${response.status}`;
      const error = new Error(`Model list request failed (${response.status}): ${detail}`);
      error.status = response.status;
      throw error;
    }

    return data;
  } finally {
    clearTimeout(timeout);
  }
}

function extractModelNames(provider, payload) {
  if (provider === 'Gemini') {
    const models = Array.isArray(payload?.models) ? payload.models : [];
    return dedupe(models.map((item) => {
      const name = item?.name || item?.displayName || '';
      return String(name).replace(/^models\//, '').trim();
    }));
  }

  const dataList = Array.isArray(payload?.data)
    ? payload.data
    : Array.isArray(payload?.models)
      ? payload.models
      : [];

  return dedupe(dataList.map((item) => {
    if (!item || typeof item !== 'object') {
      return '';
    }
    return normalizeString(item.id || item.name || item.display_name || item.displayName);
  }));
}

function buildEndpointCandidates(provider, baseUrl, apiKey) {
  if (!baseUrl) {
    return [];
  }

  if (provider === 'Gemini') {
    const direct = /\/v\d+(beta\d+)?$/i.test(baseUrl)
      ? buildUrl(baseUrl, `models?key=${encodeURIComponent(apiKey)}`)
      : buildUrl(baseUrl, `v1beta/models?key=${encodeURIComponent(apiKey)}`);
    return dedupe([direct]);
  }

  const directModels = buildUrl(baseUrl, 'models');
  const v1Models = buildUrl(baseUrl, 'v1/models');
  const alreadyVersioned = /\/(v\d+(beta\d+)?|api\/v\d+)$/i.test(baseUrl);

  return dedupe(alreadyVersioned ? [directModels] : [directModels, v1Models]);
}

function buildHeaders(provider, apiKey) {
  if (provider === 'Anthropic') {
    return {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    };
  }

  if (provider === 'Gemini') {
    return {};
  }

  return {
    Authorization: `Bearer ${apiKey}`,
  };
}

async function fetchModelsForProfile(profile = {}) {
  const validation = validateProfile(profile);
  if (!validation.ok) {
    throw new Error(validation.errors.join(' '));
  }

  const provider = normalizeString(profile.provider);
  const apiKey = normalizeString(profile.apiKey);
  if (!apiKey) {
    throw new Error('API Key is required before loading models.');
  }

  const baseUrl = normalizeBaseUrl(provider, profile.baseUrl);
  if (!baseUrl) {
    throw new Error('Base URL is required for this provider.');
  }

  const candidates = buildEndpointCandidates(provider, baseUrl, apiKey);
  const headers = buildHeaders(provider, apiKey);

  let lastError = null;

  for (const url of candidates) {
    try {
      const payload = await requestJson(url, headers);
      const models = extractModelNames(provider, payload);
      if (!models.length) {
        throw new Error('Provider returned no selectable models.');
      }
      return {
        ok: true,
        provider,
        baseUrl,
        models,
      };
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error('Unable to load models for the selected provider.');
}

module.exports = {
  SUPPORTED_PROVIDERS,
  DEFAULT_BASE_URLS,
  normalizeBaseUrl,
  validateProfile,
  fetchModelsForProfile,
};
