const { defaultAgents, defaultProfiles, defaultSessions } = require('./seedState');
const { readJson, writeJson } = require('../storage/jsonStore');
const { listAgents, saveAgents } = require('./agentService');
const { listProfiles, saveProfiles } = require('./profileRegistryService');
const { listSessions, saveSessions } = require('./sessionService');
const { getFilePaths } = require('./paths');

function loadState() {
  const files = getFilePaths();
  const persisted = readJson(files.appState, {});
  return {
    sessions: listSessions() || defaultSessions,
    agents: listAgents() || defaultAgents,
    profiles: listProfiles() || defaultProfiles,
    activeSessionId: persisted.activeSessionId || null,
    activeProfileId: persisted.activeProfileId || null,
    bookmarkColors: persisted.bookmarkColors && typeof persisted.bookmarkColors === 'object'
      ? persisted.bookmarkColors
      : undefined,
    uiTheme: persisted.uiTheme || undefined,
  };
}

function saveState(payload) {
  const files = getFilePaths();
  const nextState = {
    sessions: Array.isArray(payload?.sessions) ? payload.sessions : defaultSessions,
    agents: Array.isArray(payload?.agents) ? payload.agents : defaultAgents,
    profiles: Array.isArray(payload?.profiles) ? payload.profiles : defaultProfiles,
    activeSessionId: payload?.activeSessionId || null,
    activeProfileId: payload?.activeProfileId || null,
    bookmarkColors: payload?.bookmarkColors && typeof payload.bookmarkColors === 'object'
      ? payload.bookmarkColors
      : undefined,
    uiTheme: payload?.uiTheme || undefined,
  };

  saveSessions(nextState.sessions);
  saveAgents(nextState.agents);
  saveProfiles(nextState.profiles);
  writeJson(files.appState, {
    activeSessionId: nextState.activeSessionId,
    activeProfileId: nextState.activeProfileId,
    bookmarkColors: nextState.bookmarkColors,
    uiTheme: nextState.uiTheme,
  });

  return { ok: true };
}

module.exports = {
  loadState,
  saveState,
};
