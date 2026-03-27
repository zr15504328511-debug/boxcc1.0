const { readJson, writeJson } = require('../storage/jsonStore');
const { defaultProfiles } = require('./seedState');
const { getFilePaths } = require('./paths');

function cloneDefaultProfiles() {
  return JSON.parse(JSON.stringify(defaultProfiles));
}

function normalizeProfile(profile = {}) {
  return {
    id: profile.id || Date.now().toString(),
    name: profile.name || '个人配置',
    provider: profile.provider || 'OpenAI',
    baseUrl: profile.baseUrl || '',
    apiKey: profile.apiKey || '',
    model: profile.model || '',
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
