const fs = require('fs');
const { app, BrowserWindow, Menu, clipboard, ipcMain } = require('electron');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const http = require('http');
const { loadState, saveState } = require('./main/services/stateService');
const { listSessions, saveSessions, createSession } = require('./main/services/sessionService');
const { listProfiles, saveProfiles } = require('./main/services/profileRegistryService');
const { listAgents, saveAgents } = require('./main/services/agentService');
const { SUPPORTED_PROVIDERS, validateProfile, fetchModelsForProfile } = require('./main/services/providerResolverService');

const PYTHON_BACKEND_PORT = 18900;
const PYTHON_BACKEND_URL = `http://127.0.0.1:${PYTHON_BACKEND_PORT}`;
const HEALTH_CHECK_INTERVAL = 500;
const HEALTH_CHECK_TIMEOUT = 30000;
const BACKEND_REQUEST_TIMEOUT = 1800000;

let pythonProcess = null;
let backendStartupPromise = null;

function getPythonCandidates() {
  const candidates = [
    { command: path.join(__dirname, '.venv', 'bin', 'python'), args: [], source: 'project virtualenv' },
    { command: path.join(__dirname, '.venv', 'Scripts', 'python.exe'), args: [], source: 'project virtualenv' },
  ];
  if (process.env.BOXCC_PYTHON) {
    candidates.push({ command: process.env.BOXCC_PYTHON, args: [], source: 'BOXCC_PYTHON' });
  }

  if (process.platform === 'win32') {
    candidates.push(
      { command: 'python', args: [], source: 'PATH' },
      { command: 'py', args: ['-3'], source: 'Python launcher' },
    );
  } else if (process.platform === 'darwin') {
    candidates.push(
      { command: '/opt/homebrew/bin/python3', args: [], source: 'Homebrew Apple Silicon' },
      { command: '/opt/homebrew/bin/python3.12', args: [], source: 'Homebrew Apple Silicon' },
      { command: '/opt/homebrew/opt/python@3.12/bin/python3.12', args: [], source: 'Homebrew python@3.12' },
      { command: '/usr/local/bin/python3', args: [], source: 'Homebrew Intel' },
      { command: '/usr/local/bin/python3.12', args: [], source: 'Homebrew Intel' },
      { command: '/usr/local/opt/python@3.12/bin/python3.12', args: [], source: 'Homebrew python@3.12' },
      { command: '/Library/Frameworks/Python.framework/Versions/Current/bin/python3', args: [], source: 'python.org framework' },
      { command: 'python3.12', args: [], source: 'PATH' },
      { command: 'python3', args: [], source: 'PATH' },
      { command: 'python', args: [], source: 'PATH' },
    );
  } else {
    candidates.push(
      { command: 'python3', args: [], source: 'PATH' },
      { command: 'python', args: [], source: 'PATH' },
    );
  }

  return candidates;
}

function resolvePythonCommand() {
  for (const candidate of getPythonCandidates()) {
    const result = spawnSync(candidate.command, [
      ...candidate.args,
      '-c',
      'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)',
    ], { stdio: 'ignore' });

    if (result.status === 0) {
      safeLog('log', `[Python] Using ${candidate.command} (${candidate.source})`);
      return candidate;
    }
  }

  throw new Error('Python 3.11+ was not found. Install Python 3.11+ or set BOXCC_PYTHON to its executable path.');
}

function getBackendDir() {
  if (!app.isPackaged) return path.join(__dirname, 'backend');
  return path.join(process.resourcesPath, 'app.asar.unpacked', 'backend');
}

function safeLog(method, ...args) {
  const line = [new Date().toISOString(), method.toUpperCase(), ...args]
    .map((item) => (typeof item === 'string' ? item : String(item)))
    .join(' ');

  try {
    fs.appendFileSync(path.join(__dirname, 'debug.log'), line + '\n', 'utf8');
  } catch {}
}

function startPythonBackend() {
  const backendDir = getBackendDir();
  const python = resolvePythonCommand();
  const backendDataDir = path.join(app.getPath('userData'), 'backend-data');

  pythonProcess = spawn(python.command, [...python.args, '-m', 'app.main'], {
    cwd: backendDir,
    env: {
      ...process.env,
      BOXCC_BACKEND_DATA_DIR: backendDataDir,
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  pythonProcess.stdout.on('data', (data) => safeLog('log', `[Python] ${data.toString().trim()}`));
  pythonProcess.stderr.on('data', (data) => safeLog('error', `[Python] ${data.toString().trim()}`));
  pythonProcess.on('error', (err) => safeLog('error', '[Python] Failed to start:', err.message));
  pythonProcess.on('exit', (code, signal) => {
    safeLog('log', `[Python] Exited with code=${code} signal=${signal}`);
    pythonProcess = null;
  });
  return pythonProcess;
}

function isBackendHealthy(timeoutMs = 2000) {
  return new Promise((resolve) => {
    const req = http.get(`${PYTHON_BACKEND_URL}/health`, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      resolve(false);
    });
  });
}

function waitForHealthCheck() {
  return new Promise((resolve, reject) => {
    const startTime = Date.now();
    async function check() {
      if (Date.now() - startTime > HEALTH_CHECK_TIMEOUT) {
        return reject(new Error('Python backend health check timed out'));
      }
      if (await isBackendHealthy()) {
        safeLog('log', '[Python] Backend is healthy');
        return resolve();
      }
      setTimeout(check, HEALTH_CHECK_INTERVAL);
    }
    check();
  });
}

async function ensurePythonBackendReady(options = {}) {
  const { forceRestart = false } = options;
  if (!forceRestart && await isBackendHealthy()) return;
  if (backendStartupPromise) return backendStartupPromise;

  backendStartupPromise = (async () => {
    if (forceRestart && pythonProcess) {
      safeLog('warn', '[Electron] Restarting Python backend on demand');
      await stopPythonBackend();
    }
    if (!await isBackendHealthy()) {
      safeLog('log', '[Electron] Starting Python backend...');
      startPythonBackend();
    }
    await waitForHealthCheck();
    safeLog('log', '[Electron] Python backend ready');
  })().finally(() => {
    backendStartupPromise = null;
  });

  return backendStartupPromise;
}

function stopPythonBackend() {
  if (!pythonProcess) return Promise.resolve();
  return new Promise((resolve) => {
    pythonProcess.on('exit', () => resolve());
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(pythonProcess.pid), '/f', '/t']);
    } else {
      pythonProcess.kill('SIGTERM');
    }
    setTimeout(() => {
      if (pythonProcess) pythonProcess.kill('SIGKILL');
      resolve();
    }, 5000);
  });
}

function buildRequestBody(payload, extra = {}) {
  return {
    session_id: payload.sessionId,
    message: payload.message,
    model_name: payload.modelName || null,
    runtime_model: payload.runtimeModel || null,
    ...extra,
  };
}

function callPythonBackend(method, apiPath, body = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(apiPath, PYTHON_BACKEND_URL);
    const req = http.request({
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method,
      headers: { 'Content-Type': 'application/json' },
      timeout: BACKEND_REQUEST_TIMEOUT,
    }, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch { resolve(data); }
      });
    });

    req.on('error', (err) => reject(err));
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

function streamPythonBackend(apiPath, body, onEvent) {
  return new Promise((resolve, reject) => {
    const url = new URL(apiPath, PYTHON_BACKEND_URL);
    const req = http.request({
      hostname: url.hostname,
      port: url.port,
      path: url.pathname,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      timeout: BACKEND_REQUEST_TIMEOUT,
    }, (res) => {
      if (res.statusCode && res.statusCode >= 400) {
        let errorData = '';
        res.on('data', (chunk) => { errorData += chunk.toString('utf8'); });
        res.on('end', () => reject(new Error(errorData || `HTTP ${res.statusCode}`)));
        return;
      }

      let buffer = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => {
        buffer += chunk;
        let index = buffer.indexOf('\n\n');
        while (index >= 0) {
          const rawEvent = buffer.slice(0, index);
          buffer = buffer.slice(index + 2);
          const dataLines = rawEvent.split(/\r?\n/).filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trimStart());
          if (dataLines.length > 0) {
            try {
              onEvent(JSON.parse(dataLines.join('\n')));
            } catch (err) {
              safeLog('warn', '[chat:stream] Failed to parse SSE payload:', err.message);
            }
          }
          index = buffer.indexOf('\n\n');
        }
      });
      res.on('end', () => resolve());
    });

    req.on('error', (err) => reject(err));
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
    req.write(JSON.stringify(body));
    req.end();
  });
}

function mapBackendAgentsForUi(backendAgents, localAgents = []) {
  const localMap = new Map((Array.isArray(localAgents) ? localAgents : []).map((agent) => [agent.id, agent]));
  return (Array.isArray(backendAgents) ? backendAgents : []).map((agent) => {
    const local = localMap.get(agent.id) || {};
    return {
      id: agent.id,
      name: agent.name || agent.display_name || agent.id,
      desc: agent.description || local.desc || '',
      enabled: agent.enabled !== false,
      instructions: agent.instructions || local.instructions || '',
      isDefault: true,
      binding: local.binding || 'auto',
      phase: agent.phase || local.phase || 'worker',
      nativeName: agent.name || local.nativeName || '',
    };
  });
}

async function listEffectiveAgentsForUi() {
  const localAgents = listAgents();
  try {
    await ensurePythonBackendReady();
    const backendAgents = await callPythonBackend('GET', '/api/agents');
    const mapped = mapBackendAgentsForUi(backendAgents, localAgents);
    if (mapped.length > 0) return mapped;
  } catch (err) {
    safeLog('warn', '[agents:list] Falling back to local agent cache:', err.message);
  }
  return localAgents;
}

function createEditContextMenu(win, params) {
  const template = [];
  if (params.selectionText) template.push({ label: '\u590d\u5236', click: () => win.webContents.copy() });
  if (params.isEditable) {
    if (template.length > 0) template.push({ type: 'separator' });
    template.push(
      { label: '\u526a\u5207', click: () => win.webContents.cut() },
      { label: '\u590d\u5236', click: () => win.webContents.copy() },
      { label: '\u7c98\u8d34', click: () => win.webContents.paste() },
      { label: '\u5168\u9009', click: () => win.webContents.selectAll() },
    );
  }
  return template.length > 0 ? Menu.buildFromTemplate(template) : null;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    title: 'boxcc',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  Menu.setApplicationMenu(null);

  win.webContents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown' || !(input.control || input.meta)) return;
    const key = String(input.key || '').toLowerCase();
    if (key === 'c') { event.preventDefault(); win.webContents.copy(); }
    else if (key === 'x') { event.preventDefault(); win.webContents.cut(); }
    else if (key === 'v') { event.preventDefault(); win.webContents.paste(); }
    else if (key === 'a') { event.preventDefault(); win.webContents.selectAll(); }
  });

  win.webContents.on('context-menu', (_event, params) => {
    const menu = createEditContextMenu(win, params);
    if (menu) menu.popup({ window: win });
  });

  win.webContents.on('console-message', (_event, level, message, line, sourceId) => safeLog('error', `[Renderer:${level}] ${message} (${sourceId}:${line})`));
  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => safeLog('error', `[Renderer] did-fail-load code=${errorCode} url=${validatedURL} error=${errorDescription}`));
  win.webContents.on('render-process-gone', (_event, details) => safeLog('error', `[Renderer] render-process-gone reason=${details.reason} exitCode=${details.exitCode}`));
  win.webContents.on('preload-error', (_event, preloadPath, error) => safeLog('error', `[Renderer] preload-error path=${preloadPath} error=${error?.message || error}`));
  win.webContents.on('did-finish-load', () => {
    safeLog('log', '[Renderer] did-finish-load');
    setTimeout(() => {
      win.webContents.executeJavaScript(`(() => ({ rootHtmlLength: document.getElementById('root')?.innerHTML?.length || 0, bodyText: (document.body?.innerText || '').slice(0, 120) }))()`).then((snapshot) => {
        safeLog('log', '[Renderer] snapshot', JSON.stringify(snapshot));
      }).catch((error) => {
        safeLog('error', '[Renderer] snapshot failed', error?.message || error);
      });
    }, 1000);
  });

  const devUrl = process.env.BOXCC_RENDERER_DEV_URL;
  if (devUrl) {
    win.loadURL(devUrl);
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    win.loadFile(path.join(__dirname, 'dist', 'renderer', 'index.html'));
  }
}

app.whenReady().then(async () => {
  ipcMain.handle('app-state:load', async () => {
    const state = loadState();
    state.agents = await listEffectiveAgentsForUi();
    return state;
  });
  ipcMain.handle('app-state:save', async (_event, payload) => saveState(payload));
  ipcMain.handle('sessions:list', async () => listSessions());
  ipcMain.handle('sessions:save', async (_event, payload) => saveSessions(payload));
  ipcMain.handle('sessions:create', async (_event, payload) => createSession(payload));
  ipcMain.handle('profiles:list', async () => listProfiles());
  ipcMain.handle('profiles:save', async (_event, payload) => saveProfiles(payload));
  ipcMain.handle('agents:list', async () => listEffectiveAgentsForUi());
  ipcMain.handle('agents:save', async (_event, payload) => saveAgents(payload));
  ipcMain.handle('providers:list', async () => SUPPORTED_PROVIDERS);
  ipcMain.handle('providers:validate-profile', async (_event, payload) => validateProfile(payload));
  ipcMain.handle('providers:list-models', async (_event, payload) => fetchModelsForProfile(payload));
  ipcMain.handle('clipboard:write-text', async (_event, payload) => { clipboard.writeText(String(payload || '')); return true; });

  ipcMain.handle('chat:send', async (_event, payload) => {
    try {
      const requestBody = buildRequestBody(payload);
      await ensurePythonBackendReady();
      let result;
      try {
        result = await callPythonBackend('POST', '/api/chat', requestBody);
      } catch (err) {
        if (err?.code === 'ECONNREFUSED' || String(err?.message || '').includes('ECONNREFUSED')) {
          safeLog('warn', '[chat:send] Backend refused connection, restarting once');
          await ensurePythonBackendReady({ forceRestart: true });
          result = await callPythonBackend('POST', '/api/chat', requestBody);
        } else {
          throw err;
        }
      }
      if (result.ok) {
        return { ok: true, userMessage: { id: `user-${Date.now()}`, role: 'user', content: payload.message, createdAt: new Date().toLocaleTimeString() }, assistantMessage: result.message, title: result.title || null, department_results: result.department_results || null, workflow_artifact: result.workflow_artifact || null };
      }
      return { ok: false, error: result.detail || 'Unknown error from backend' };
    } catch (err) {
      safeLog('error', '[chat:send] Error calling Python backend:', err.message);
      return { ok: false, error: `Backend error: ${err.message}` };
    }
  });

  ipcMain.handle('chat:stream-start', async (event, payload) => {
    const requestId = `stream-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const sender = event.sender;
    const requestBody = buildRequestBody(payload, { stream: true });

    try {
      await ensurePythonBackendReady();
    } catch (err) {
      return { ok: false, error: `Backend error: ${err.message}` };
    }

    const pushEvent = (streamEvent) => {
      if (!sender.isDestroyed()) sender.send('chat:stream-event', { requestId, ...streamEvent });
    };

    setTimeout(() => {
      (async () => {
        try {
          try {
            await streamPythonBackend('/api/chat', requestBody, pushEvent);
          } catch (err) {
            if (err?.code === 'ECONNREFUSED' || String(err?.message || '').includes('ECONNREFUSED')) {
              safeLog('warn', '[chat:stream] Backend refused connection, restarting once');
              await ensurePythonBackendReady({ forceRestart: true });
              await streamPythonBackend('/api/chat', requestBody, pushEvent);
            } else {
              throw err;
            }
          }
        } catch (err) {
          safeLog('error', '[chat:stream] Error calling Python backend:', err.message);
          pushEvent({ type: 'error', error: `Backend error: ${err.message}` });
        }
      })();
    }, 0);

    return { ok: true, requestId };
  });

  try {
    await ensurePythonBackendReady();
  } catch (err) {
    safeLog('error', '[Electron] Python backend failed to start:', err.message);
  }

  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('will-quit', async (event) => {
  if (pythonProcess) {
    event.preventDefault();
    safeLog('log', '[Electron] Stopping Python backend...');
    await stopPythonBackend();
    app.quit();
  }
});
