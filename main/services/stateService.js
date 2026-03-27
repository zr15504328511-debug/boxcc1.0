const { defaultAgents, defaultProfiles, defaultSessions } = require('./seedState');
const { listAgents, saveAgents } = require('./agentService');
const { listProfiles, saveProfiles } = require('./profileRegistryService');
const { listSessions, saveSessions } = require('./sessionService');

function loadState() {
  return {
    sessions: listSessions() || defaultSessions,
    agents: listAgents() || defaultAgents,
    profiles: listProfiles() || defaultProfiles,
  };
}

function saveState(payload) {
  const nextState = {
    sessions: Array.isArray(payload?.sessions) ? payload.sessions : defaultSessions,
    agents: Array.isArray(payload?.agents) ? payload.agents : defaultAgents,
    profiles: Array.isArray(payload?.profiles) ? payload.profiles : defaultProfiles,
  };

  saveSessions(nextState.sessions);
  saveAgents(nextState.agents);
  saveProfiles(nextState.profiles);

  return { ok: true };
}

module.exports = {
  loadState,
  saveState,
};
