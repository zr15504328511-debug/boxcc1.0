const path = require('path');
const { app } = require('electron');
const { ensureDir } = require('../storage/jsonStore');

function getDataDir() {
  const dataDir = path.join(app.getPath('userData'), 'data');
  ensureDir(dataDir);
  return dataDir;
}

function getFilePaths() {
  const dataDir = getDataDir();
  return {
    appState: path.join(dataDir, 'app-state.json'),
    sessions: path.join(dataDir, 'sessions.json'),
    agents: path.join(dataDir, 'agents.json'),
    profiles: path.join(dataDir, 'profiles.json'),
  };
}

module.exports = {
  getDataDir,
  getFilePaths,
};
