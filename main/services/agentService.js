const { readJson, writeJson } = require('../storage/jsonStore');
const { defaultAgents } = require('./seedState');
const { getFilePaths } = require('./paths');

function cloneDefaultAgents() {
  return JSON.parse(JSON.stringify(defaultAgents));
}

function listAgents() {
  const files = getFilePaths();
  const storedAgents = readJson(files.agents, cloneDefaultAgents());
  const storedMap = new Map((Array.isArray(storedAgents) ? storedAgents : []).map((agent) => [agent.id, agent]));

  const mergedDefaults = cloneDefaultAgents().map((agent) => {
    const stored = storedMap.get(agent.id) || {};
    return {
      ...agent,
      ...stored,
      name: agent.name,
      desc: agent.desc,
      isDefault: true,
      binding: stored.binding || agent.binding,
      enabled: stored.enabled !== false,
      instructions: stored.instructions || agent.instructions,
    };
  });
  const defaultIds = new Set(mergedDefaults.map((agent) => agent.id));
  const customAgents = (Array.isArray(storedAgents) ? storedAgents : [])
    .filter((agent) => agent?.id && !defaultIds.has(agent.id))
    .map((agent) => ({
      ...agent,
      name: agent.name || agent.display_name || agent.id,
      desc: agent.desc || agent.description || '',
      enabled: agent.enabled !== false,
      isDefault: false,
      binding: agent.binding || 'auto',
      phase: agent.phase || 'worker',
      instructions: agent.instructions || agent.system_prompt || '',
    }));
  return [...mergedDefaults, ...customAgents];
}

function saveAgents(agents) {
  const files = getFilePaths();
  const nextAgents = Array.isArray(agents) ? agents : cloneDefaultAgents();
  writeJson(files.agents, nextAgents);
  return nextAgents;
}

module.exports = {
  listAgents,
  saveAgents,
};
