const { readJson, writeJson } = require('../storage/jsonStore');
const { defaultSessions } = require('./seedState');
const { getFilePaths } = require('./paths');

function cloneDefaultSessions() {
  return JSON.parse(JSON.stringify(defaultSessions));
}

function normalizeSession(session = {}) {
  return {
    ...session,
    uploads: Array.isArray(session.uploads) ? session.uploads : [],
    messages: Array.isArray(session.messages) ? session.messages : [],
    agentContexts: session.agentContexts && typeof session.agentContexts === 'object'
      ? session.agentContexts
      : {},
  };
}

function listSessions() {
  const files = getFilePaths();
  const sessions = readJson(files.sessions, cloneDefaultSessions());
  const normalized = Array.isArray(sessions)
    ? sessions.map(normalizeSession)
    : cloneDefaultSessions();

  const seed = cloneDefaultSessions()[0];
  return normalized.map((session) => {
    if (session.id === seed.id && session.messages.length === 0) {
      return {
        ...session,
        title: seed.title,
        summary: seed.summary,
        memorySummary: seed.memorySummary,
        uploads: session.uploads.length ? session.uploads : seed.uploads,
      };
    }
    return session;
  });
}

function saveSessions(sessions) {
  const files = getFilePaths();
  const nextSessions = Array.isArray(sessions) ? sessions : cloneDefaultSessions();
  writeJson(files.sessions, nextSessions);
  return nextSessions;
}

function createSession(partial = {}) {
  const sessions = listSessions();
  const now = new Date();
  const session = {
    id: partial.id || now.getTime().toString(),
    title: partial.title || '新会话',
    updatedAt: partial.updatedAt || now.toLocaleTimeString(),
    summary: partial.summary || '',
    memorySummary: partial.memorySummary || 'Waiting...',
    uploads: Array.isArray(partial.uploads) ? partial.uploads : [],
    messages: Array.isArray(partial.messages) ? partial.messages : [],
    agentContexts: partial.agentContexts && typeof partial.agentContexts === 'object'
      ? partial.agentContexts
      : {},
  };

  const nextSessions = [session, ...sessions];
  saveSessions(nextSessions);
  return session;
}

module.exports = {
  listSessions,
  saveSessions,
  createSession,
};
