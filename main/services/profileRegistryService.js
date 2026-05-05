const { readJson, writeJson } = require('../storage/jsonStore');
const { defaultProfiles } = require('./seedState');
const { getFilePaths } = require('./paths');

function cloneDefaultProfiles() {
  return JSON.parse(JSON.stringify(defaultProfiles));
}

function normalizeProfile(profile = {}) {
  const name = profile.name || profile.label || '个人配置';
  const label = profile.label || profile.name || '个人配置';
  const models = Array.isArray(profile.models) ? profile.models : [];
  return {
    id: profile.id || Date.now().toString(),
    name,
    label,
    provider: profile.provider || 'OpenAI',
    baseUrl: profile.baseUrl || '',
    apiKey: profile.apiKey || '',
    model: profile.model || '',
    models,
    temperature: typeof profile.temperature === 'number' ? profile.temperature : undefined,
    maxTokens: typeof profile.maxTokens === 'number' ? profile.maxTokens : undefined,
  };
}

function listProfiles() {
  const files = getFilePaths();
  const profiles = readJson(files.profiles, cloneDefaultProfiles());
  return Array.isArray(profiles) ? profiles.map(normalizeProfile) : cloneDefaultProfiles();
}

function saveProfiles(profiles) {
  const files = getFilePaths();
  const nextProfiles = Array.isArray(profiles)
    ? profiles.map(normalizeProfile)
    : cloneDefaultProfiles();

  writeJson(files.profiles, nextProfiles);
  return nextProfiles;
}

module.exports = {
  listProfiles,
  saveProfiles,
  normalizeProfile,
};
