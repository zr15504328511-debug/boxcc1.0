const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('boxccAPI', {
  loadState: () => ipcRenderer.invoke('app-state:load'),
  saveState: (payload) => ipcRenderer.invoke('app-state:save', payload),
  loadSessions: () => ipcRenderer.invoke('sessions:list'),
  saveSessions: (payload) => ipcRenderer.invoke('sessions:save', payload),
  createSession: (payload) => ipcRenderer.invoke('sessions:create', payload),
  loadProfiles: () => ipcRenderer.invoke('profiles:list'),
  saveProfiles: (payload) => ipcRenderer.invoke('profiles:save', payload),
  loadAgents: () => ipcRenderer.invoke('agents:list'),
  saveAgents: (payload) => ipcRenderer.invoke('agents:save', payload),
  listProviders: () => ipcRenderer.invoke('providers:list'),
  validateProfile: (payload) => ipcRenderer.invoke('providers:validate-profile', payload),
  listModelsForProfile: (payload) => ipcRenderer.invoke('providers:list-models', payload),
  sendChat: (payload) => ipcRenderer.invoke('chat:send', payload),
  startChatStream: (payload) => ipcRenderer.invoke('chat:stream-start', payload),
  onChatStreamEvent: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on('chat:stream-event', listener);
    return () => ipcRenderer.removeListener('chat:stream-event', listener);
  },
  copyText: (payload) => ipcRenderer.invoke('clipboard:write-text', payload),
});
