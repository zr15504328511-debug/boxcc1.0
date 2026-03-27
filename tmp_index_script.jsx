
        const { useState, useEffect, useRef } = React;

        const DEFAULT_DEPARTMENT_AGENTS = [
            { id: 'orc', name: 'Orchestrator', desc: '????????????????', enabled: true, instructions: '??????????????????????????', isDefault: true, binding: 'auto' },
            { id: 'dom', name: 'Domain Expert', desc: '?????????????????', enabled: true, instructions: '??????????????????????', isDefault: true, binding: 'auto' },
            { id: 'pln', name: 'Planner', desc: '???????????SKU ?????', enabled: true, instructions: '????????????SKU ????????', isDefault: true, binding: 'auto' },
            { id: 'ana', name: 'Analyst', desc: '????????????????', enabled: true, instructions: '????????????????????', isDefault: true, binding: 'auto' },
            { id: 'crt', name: 'Critic', desc: '??????????????', enabled: true, instructions: '??????????????????????????', isDefault: true, binding: 'auto' },
            { id: 'cpy', name: 'Copywriter', desc: '???????????????', enabled: true, instructions: '????????????????????', isDefault: true, binding: 'auto' }
        ];

        function normalizeDepartmentAgents(existingAgents) {
            const incoming = Array.isArray(existingAgents) ? existingAgents : [];
            const incomingMap = new Map(incoming.map(agent => [agent.id, agent]));

            return DEFAULT_DEPARTMENT_AGENTS.map((agent) => {
                const existing = incomingMap.get(agent.id);
                return existing ? { ...agent, ...existing } : agent;
            });
        }

        const App = () => {
            const hasHydrated = useRef(false);
            const inputRef = useRef(null);
            const saveTimerRef = useRef(null);
            const errorTimerRef = useRef(null);
            const uploadInputRef = useRef(null);
            const modelFetchTimerRef = useRef({});

            const [theme, setTheme] = useState('win98');

            const [sessions, setSessions] = useState([
                {
                    id: '1',
                    title: '2024??????',
                    updatedAt: '14:20',
                    summary: '??????',
                    memorySummary: '???????????????',
                    uploads: [{ id: 'f1', name: '澶忚鎶ヤ环琛?xlsx', size: '24KB' }],
                    messages: []
                }
            ]);

            const [activeId, setActiveId] = useState('1');
            const [agents, setAgents] = useState(DEFAULT_DEPARTMENT_AGENTS /*
                { id: 'gen', name: 'General', desc: '鍩虹閫昏緫鎺ㄧ悊', enabled: true, instructions: '鍩虹瀵硅瘽涓庨€昏緫澶勭悊', isDefault: true },
                { id: 'knw', name: 'Knowledge', desc: '鏈嶈宸ヨ壓鐭ヨ瘑搴?, enabled: true, instructions: '鏈嶈宸ヨ壓涓庨潰鏂欑煡璇嗗簱', isDefault: true },
                { id: 'pln', name: 'Planning', desc: '浼佸垝鎺掓湡绠＄悊', enabled: false, instructions: '瀛ｈ妭鎬у晢鍝佷紒鍒掓帓鏈?, isDefault: true },
                { id: 'ana', name: 'Analysis', desc: '瓒嬪娍涓庢暟鎹垎鏋?, enabled: true, instructions: '閿€鍞暟鎹笌瓒嬪娍鍒嗘瀽', isDefault: true },
                { id: 'doc', name: 'Document', desc: '璐熻矗琛ㄦ牸鍜?PPT', enabled: true, instructions: '澶勭悊鏂囨。銆佸鍑鸿〃鏍间笌鐢熸垚PPT', isDefault: true },
                { id: 'src', name: 'Search', desc: '鏃跺皻璧勮瀹炴椂鎼滅储', enabled: false, instructions: '澶栭儴鏃跺皻鍜ㄨ瀹炴椂鎼滅储', isDefault: true },
                { id: 'img', name: 'imagen', desc: '鍥惧儚鐢熸垚涓庢彁绀鸿瘝', enabled: true, instructions: '鐢熸垚鍥惧儚鎻愮ず璇嶄笌瑙嗚鏂规', isDefault: true }
            */);

            const [profiles, setProfiles] = useState([
                { id: 'p1', name: '????1', provider: 'OpenAI', baseUrl: '', apiKey: '', model: 'gpt-4o' }
            ]);
            const [providerOptions, setProviderOptions] = useState(['OpenAI', 'Anthropic', 'Gemini', 'OpenRouter', 'Custom']);
            const [profileModelState, setProfileModelState] = useState({});

            const [isSettingsOpen, setIsSettingsOpen] = useState(false);
            const [isAgentOpen, setIsAgentOpen] = useState(false);
            const [isSourceOpen, setIsSourceOpen] = useState(false);
            const [editingAgent, setEditingAgent] = useState(null);
            const [renamingSessionId, setRenamingSessionId] = useState(null);
            const [renameInput, setRenameInput] = useState('');
            const [input, setInput] = useState('');
            const [draggedTabId, setDraggedTabId] = useState(null);
            const [runtimeError, setRuntimeError] = useState('');
            const [confirmState, setConfirmState] = useState({ open: false, kind: null, id: null, message: '' });

            useEffect(() => {
                const handleWindowError = (event) => {
                    const message = event?.error?.message || event?.message || 'Unknown renderer error';
                    setRuntimeError(message);
                };

                window.addEventListener('error', handleWindowError);
                return () => window.removeEventListener('error', handleWindowError);
            }, []);

            useEffect(() => {
                if (!runtimeError) return;

                clearTimeout(errorTimerRef.current);
                errorTimerRef.current = setTimeout(() => {
                    setRuntimeError('');
                }, 2600);

                return () => clearTimeout(errorTimerRef.current);
            }, [runtimeError]);

            useEffect(() => {
                if (!window.boxccAPI?.listProviders) return;

                window.boxccAPI.listProviders().then((list) => {
                    if (Array.isArray(list) && list.length) {
                        setProviderOptions(list);
                    }
                }).catch((error) => {
                    console.error('Failed to load provider list', error);
                });
            }, []);

            useEffect(() => {
                if (!window.boxccAPI?.loadState) return;

                window.boxccAPI.loadState().then((state) => {
                    if (state?.sessions?.length) {
                        setSessions(state.sessions);
                        setActiveId(state.sessions[0].id);
                    }
                    if (state?.agents?.length) {
                        setAgents(normalizeDepartmentAgents(state.agents));
                    }
                    if (state?.profiles?.length) {
                        setProfiles(state.profiles);
                    }
                    hasHydrated.current = true;
                }).catch((error) => {
                    console.error('Failed to load app state', error);
                    setAgents(normalizeDepartmentAgents(DEFAULT_DEPARTMENT_AGENTS));
                    hasHydrated.current = true;
                });
            }, []);

            useEffect(() => {
                if (!hasHydrated.current || !window.boxccAPI?.saveState) return;
                clearTimeout(saveTimerRef.current);
                saveTimerRef.current = setTimeout(() => {
                    window.boxccAPI.saveState({ sessions, agents, profiles }).catch((error) => {
                        console.error('Failed to save app state', error);
                    });
                }, 120);

                return () => clearTimeout(saveTimerRef.current);
            }, [sessions, agents, profiles]);

            useEffect(() => {
                if (!hasHydrated.current || !window.boxccAPI?.listModelsForProfile) return;

                profiles.forEach((profile) => {
                    const provider = String(profile?.provider || '').trim();
                    const baseUrl = String(profile?.baseUrl || '').trim();
                    const apiKey = String(profile?.apiKey || '').trim();
                    const requestKey = `${provider}||${baseUrl}||${apiKey}`;
                    const currentModelState = profileModelState[profile.id];

                    if (!apiKey) {
                        clearTimeout(modelFetchTimerRef.current[profile.id]);
                        if (currentModelState?.options?.length || currentModelState?.error || currentModelState?.requestKey !== requestKey) {
                            setProfileModelState((prev) => ({
                                ...prev,
                                [profile.id]: { options: [], loading: false, error: '', requestKey },
                            }));
                        }
                        return;
                    }

                    if (currentModelState?.loading || currentModelState?.requestKey === requestKey) {
                        return;
                    }

                    clearTimeout(modelFetchTimerRef.current[profile.id]);
                    modelFetchTimerRef.current[profile.id] = setTimeout(() => {
                        refreshModelsForProfile(profile);
                    }, 700);
                });

                return () => {
                    Object.values(modelFetchTimerRef.current).forEach((timer) => clearTimeout(timer));
                };
            }, [profiles, profileModelState]);

            useEffect(() => {
                const normalized = normalizeDepartmentAgents(agents);
                const changed = JSON.stringify(normalized) !== JSON.stringify(agents);
                if (changed) {
                    setAgents(normalized);
                }
            }, []);

            useEffect(() => {
                requestAnimationFrame(() => inputRef.current?.focus());
            }, [activeId, theme]);

            useEffect(() => {
                const handleWindowFocus = () => restoreInputFocus();
                window.addEventListener('focus', handleWindowFocus);
                return () => window.removeEventListener('focus', handleWindowFocus);
            }, []);

            const current = sessions.find(s => s.id === activeId) || sessions[0] || { messages: [], uploads: [], title: 'None' };

            const updateProfile = (profileId, patch) => {
                setProfiles((prev) => prev.map((profile) => (
                    profile.id === profileId ? { ...profile, ...patch } : profile
                )));
            };

            const getProfileModelOptions = (profileId, currentModel) => {
                const loaded = Array.isArray(profileModelState[profileId]?.options)
                    ? profileModelState[profileId].options
                    : [];
                const merged = currentModel && !loaded.includes(currentModel)
                    ? [currentModel, ...loaded]
                    : loaded;
                return Array.from(new Set(merged.filter(Boolean)));
            };

            const refreshModelsForProfile = async (profile) => {
                if (!profile?.id || !window.boxccAPI?.listModelsForProfile) return;

                const provider = String(profile.provider || '').trim();
                const baseUrl = String(profile.baseUrl || '').trim();
                const apiKey = String(profile.apiKey || '').trim();
                const requestKey = `${provider}||${baseUrl}||${apiKey}`;

                if (!apiKey) {
                    setProfileModelState((prev) => ({
                        ...prev,
                        [profile.id]: { options: [], loading: false, error: '', requestKey },
                    }));
                    return;
                }

                setProfileModelState((prev) => ({
                    ...prev,
                    [profile.id]: {
                        options: Array.isArray(prev[profile.id]?.options) ? prev[profile.id].options : [],
                        loading: true,
                        error: '',
                        requestKey,
                    },
                }));

                try {
                    const result = await window.boxccAPI.listModelsForProfile({
                        provider,
                        baseUrl,
                        apiKey,
                        name: profile.name,
                    });
                    const nextOptions = Array.isArray(result?.models) ? result.models : [];

                    setProfileModelState((prev) => ({
                        ...prev,
                        [profile.id]: {
                            options: nextOptions,
                            loading: false,
                            error: '',
                            requestKey,
                        },
                    }));

                    setProfiles((prev) => prev.map((item) => {
                        if (item.id !== profile.id) return item;
                        const nextModel = nextOptions.includes(item.model) ? item.model : (nextOptions[0] || '');
                        return { ...item, model: nextModel };
                    }));
                } catch (error) {
                    setProfileModelState((prev) => ({
                        ...prev,
                        [profile.id]: {
                            options: [],
                            loading: false,
                            error: error?.message || 'Failed to load models',
                            requestKey,
                        },
                    }));
                }
            };

            const handleDragStart = (e, id) => {
                setDraggedTabId(id);
                e.dataTransfer.effectAllowed = "move";
                // Required for Firefox
                e.dataTransfer.setData("text/plain", id);
            };

            const handleDragOver = (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
            };

            const handleDrop = (e, targetId) => {
                e.preventDefault();
                if (!draggedTabId || draggedTabId === targetId) return;

                const newSessions = [...sessions];
                const draggedIndex = newSessions.findIndex(s => s.id === draggedTabId);
                const targetIndex = newSessions.findIndex(s => s.id === targetId);

                if (draggedIndex < 0 || targetIndex < 0) return;

                const [draggedItem] = newSessions.splice(draggedIndex, 1);
                newSessions.splice(targetIndex, 0, draggedItem);

                setSessions(newSessions);
                setDraggedTabId(null);
            };

            const handleAddAgent = () => {
                setRuntimeError('???????????????????? Agent?');
            };

            const handleSaveAgent = (updated) => {
                const newAgents = agents.map(a => a.id === updated.id ? updated : a);
                setAgents(newAgents);
                setEditingAgent(null);
            };

            const restoreInputFocus = () => {
                requestAnimationFrame(() => {
                    window.focus();
                    document.activeElement?.blur?.();
                    inputRef.current?.focus();
                });
            };

            const openConfirm = (kind, id, message) => {
                setConfirmState({ open: true, kind, id, message });
            };

            const closeConfirm = () => {
                setConfirmState({ open: false, kind: null, id: null, message: '' });
                restoreInputFocus();
            };

            const executeConfirm = () => {
                if (confirmState.kind === 'delete-agent') {
                    setAgents(prev => prev.filter(a => a.id !== confirmState.id));
                } else if (confirmState.kind === 'delete-session') {
                    const newSessions = sessions.filter(s => s.id !== confirmState.id);
                    setSessions(newSessions);
                    if (activeId === confirmState.id && newSessions.length > 0) setActiveId(newSessions[0].id);
                    else if (newSessions.length === 0) handleNewSession();
                } else if (confirmState.kind === 'delete-profile') {
                    setProfiles(prev => prev.filter(x => x.id !== confirmState.id));
                } else if (confirmState.kind === 'remove-upload') {
                    setSessions(prev => prev.map(s => s.id === activeId ? {
                        ...s,
                        uploads: (s.uploads || []).filter(f => f.id !== confirmState.id),
                    } : s));
                }

                setConfirmState({ open: false, kind: null, id: null, message: '' });
                restoreInputFocus();
            };

            const handleDeleteAgent = (id) => {
                openConfirm('delete-agent', id, '??????? Agent ??');
            };

            const handleDeleteSession = (e, id) => {
                e.stopPropagation();
                openConfirm('delete-session', id, '?????????????');
            };

            const handleRenameStart = () => {
                if(!current || !current.id) return;
                setRenameInput(current.title);
                setRenamingSessionId(current.id);
            };

            const handleRenameSave = () => {
                if(renameInput.trim()) {
                    setSessions(sessions.map(s => s.id === renamingSessionId ? {...s, title: renameInput.trim()} : s));
                }
                setRenamingSessionId(null);
            };

            const handleDeleteProfile = (id) => {
                openConfirm('delete-profile', id, '??????? API ????');
            };

            const requestDeleteAgent = (id) => {
                openConfirm('delete-agent', id, '??????? Agent ??');
            };

            const requestDeleteSession = (e, id) => {
                e.stopPropagation();
                openConfirm('delete-session', id, '?????????????');
            };

            const requestDeleteProfile = (id) => {
                openConfirm('delete-profile', id, '??????? API ????');
            };

            const requestRemoveUpload = (id) => {
                openConfirm('remove-upload', id, '???????????');
            };

            const handleAddProfile = () => {
                setProfiles([...profiles, { id: Date.now().toString(), name: '???', provider: 'OpenAI', baseUrl: '', apiKey: '', model: '' }]);
            };

            const handleUploadClick = () => {
                uploadInputRef.current?.click();
            };

            const handleUploadFiles = (event) => {
                const fileList = Array.from(event.target.files || []);
                if (!fileList.length) {
                    restoreInputFocus();
                    return;
                }

                const nextUploads = fileList.map((file) => ({
                    id: `${Date.now()}-${file.name}`,
                    name: file.name,
                    size: file.size ? `${Math.max(1, Math.round(file.size / 1024))}KB` : '',
                    type: file.type || '',
                }));

                setSessions((prev) => prev.map((session) => (
                    session.id === activeId
                        ? { ...session, uploads: [...(session.uploads || []), ...nextUploads] }
                        : session
                )));

                event.target.value = '';
                restoreInputFocus();
            };

            const handleNewSession = () => {
                const nid = Date.now().toString();
                const ns = { id: nid, title: '???', updatedAt: '??', messages: [], uploads: [], memorySummary: 'Waiting...', agentContexts: {} };
                setSessions([ns, ...sessions]);
                setActiveId(nid);
            };

            const handleSend = async () => {
                const message = input.trim();
                if (!message) return;

                setInput('');

                if (!window.boxccAPI?.sendChat) {
                    const msg = { id: Date.now().toString(), role: 'user', content: message, createdAt: new Date().toLocaleTimeString() };
                    setSessions(prev => prev.map(s => s.id === activeId ? {...s, messages: [...(s.messages||[]), msg]} : s));
                    requestAnimationFrame(() => inputRef.current?.focus());
                    return;
                }

                // Add user message immediately for responsiveness
                const userMsg = { id: `user-${Date.now()}`, role: 'user', content: message, createdAt: new Date().toLocaleTimeString() };
                setSessions(prev => prev.map(s => s.id === activeId ? {...s, messages: [...(s.messages||[]), userMsg]} : s));

                try {
                    const activeProfile = profiles[0];
                    const result = await window.boxccAPI.sendChat({
                        sessionId: activeId,
                        message,
                        modelName: activeProfile?.model || null,
                    });

                    if (result?.ok) {
                        setSessions(prev => prev.map(s => {
                            if (s.id !== activeId) return s;
                            const assistantMsg = result.assistantMessage ? {
                                ...result.assistantMessage,
                                createdAt: result.assistantMessage.createdAt || new Date().toLocaleTimeString(),
                            } : null;
                            const newMessages = assistantMsg ? [...s.messages, assistantMsg] : s.messages;
                            const nextAgentContexts = Array.isArray(result.department_results)
                                ? Object.fromEntries(result.department_results.map(item => [item.id, item]))
                                : (s.agentContexts || {});
                            return {
                                ...s,
                                messages: newMessages,
                                title: result.title || s.title,
                                agentContexts: nextAgentContexts,
                            };
                        }));
                    } else {
                        const errMsg = { id: `err-${Date.now()}`, role: 'assistant', content: `Error: ${result?.error || 'Unknown error'}`, createdAt: new Date().toLocaleTimeString() };
                        setSessions(prev => prev.map(s => s.id === activeId ? {...s, messages: [...s.messages, errMsg]} : s));
                    }
                } catch (error) {
                    console.error('Failed to send chat', error);
                    setRuntimeError(error?.message || 'Failed to send chat');
                } finally {
                    requestAnimationFrame(() => inputRef.current?.focus());
                }
            };

            const focusComposer = () => {
                requestAnimationFrame(() => inputRef.current?.focus());
            };

            const isAnyRightOpen = isSettingsOpen || isAgentOpen;


            return (
                <div className="theme-container" data-theme={theme}>
                    {/* Top Menu Bar */}
                    <div className="outset h-8 flex items-center px-3 justify-end text-xs gap-4" style={{ borderRadius: 0, borderTop: 0, borderLeft: 0, borderRight: 0, borderBottom: 0 }}>
                        <button 
                            className="red-dot-btn"
                            title="鍒囨崲绯荤粺椋庢牸"
                            onClick={() => setTheme(theme === 'win98' ? 'mac' : 'win98')}
                        />
                        <div className="flex items-center opacity-80">
                            <span className="bg-panel px-2 py-0.5" style={{border: 'var(--border-panel)'}}>CPU: 1.2%</span>
                        </div>
                    </div>

                    <div className="flex flex-1 overflow-hidden p-2 gap-2 bg-app">
                        
                        {/* Main Dialogue Zone */}
                        <div className="outset flex-1 flex flex-col overflow-hidden relative" style={{borderTop: 'none'}}>
                            {/* History Bar */}
                            <div className="history-strip">
                                {sessions.map(s => (
                                    <div 
                                        key={s.id} 
                                        draggable
                                        onDragStart={(e) => handleDragStart(e, s.id)}
                                        onDragOver={handleDragOver}
                                        onDrop={(e) => handleDrop(e, s.id)}
                                        className={`history-tab flex items-center justify-between gap-2 ${activeId === s.id ? 'active' : ''}`}
                                        onClick={() => setActiveId(s.id)}
                                    >
                                        <span 
                                            className="tab-title"
                                            onDoubleClick={(e) => { e.stopPropagation(); if(activeId === s.id) handleRenameStart(); }}
                                            style={{
                                                cursor: activeId === s.id ? 'text' : 'pointer',
                                                whiteSpace: 'nowrap',
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                flexGrow: 1,
                                                fontWeight: activeId === s.id ? 'bold' : 'normal'
                                            }}
                                        >
                                            {s.title}
                                        </span>
                                        <button 
                                            className="text-red-700 hover:font-bold text-[14px] ml-1 px-1 leading-none flex-shrink-0"
                                            title="鍒犻櫎浼氳瘽"
                                            onClick={(e) => requestDeleteSession(e, s.id)}
                                        >
                                            脳
                                        </button>
                                    </div>
                                ))}
                                <button 
                                    className="px-3 font-bold text-xl hover:text-blue-800" 
                                    style={{background: 'transparent', border: 'none', cursor: 'pointer', outline: 'none', marginBottom: '4px'}}
                                    title="鏂板缓浼氳瘽" 
                                    onClick={handleNewSession}
                                >
                                    +
                                </button>
                            </div>

                            {/* Session Header */}
                            <div className="p-3 bg-header border-b border-panel-dark flex justify-end items-center">
                                <button 
                                    className={`win-button ${isSourceOpen ? 'active' : ''}`} 
                                    onClick={() => setIsSourceOpen(!isSourceOpen)}
                                >
                                    馃搸 璧勬枡搴?({current.uploads?.length || 0})
                                </button>
                            </div>

                            {runtimeError && (
                                <div className="error-banner">
                                    Frontend error: {runtimeError}
                                </div>
                            )}

                            {/* Source Panel */}
                            {isSourceOpen && (
                                <div className="source-panel outset mx-2 mt-1">
                                    <input
                                        ref={uploadInputRef}
                                        type="file"
                                        multiple
                                        style={{ display: 'none' }}
                                        onChange={handleUploadFiles}
                                    />
                                    <div className="font-bold border-b border-panel-dark mb-2 flex justify-between pb-1" onClick={handleUploadClick}>
                                        <span>宸蹭笂浼犳枃浠?/span>
                                        <button className="text-xs underline" onClick={restoreInputFocus}>+ 涓婁紶鏂拌祫鏂?/button>
                                    </div>
                                    <div className="grid grid-cols-3 gap-2">
                                        {(current.uploads || []).map(f => (
                                            <div key={f.id} className="inset p-2 text-xs flex justify-between">
                                                <span>馃搫 {f.name}</span>
                                                <button className="text-red-600 font-bold" onClick={() => requestRemoveUpload(f.id)}>脳</button>
                                            </div>
                                        ))}
                                        {current.uploads?.length === 0 && <div className="text-muted text-xs italic">鏃犳枃浠?/div>}
                                    </div>
                                </div>
                            )}

                            {/* Messages */}
                            <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-msg-area">
                                {(current.messages || []).map(m => (
                                    <div key={m.id} className={`msg-bubble ${m.role === 'user' ? 'msg-user' : 'msg-assistant'}`}>
                                        <div 
                                            className="text-[10px] font-bold opacity-60 mb-1" 
                                            style={{color: theme === 'mac' && m.role === 'user' ? '#cce5ff' : 'inherit'}}
                                        >
                                            {m.role.toUpperCase()} @ {m.createdAt}
                                        </div>
                                        <div>{m.content}</div>
                                    </div>
                                ))}
                            </div>

                            {/* Input */}
                            <div
                                className="p-3 bg-panel border-t border-panel-dark composer-panel"
                                onMouseDown={focusComposer}
                            >
                                <div className="flex gap-2">
                                    <textarea 
                                        ref={inputRef}
                                        className="flex-1 h-20 resize-none p-2" 
                                        placeholder="杈撳叆浼佸垝鎸囦护..." 
                                        value={input}
                                        autoFocus
                                        onChange={e => setInput(e.target.value)}
                                        onKeyDown={e => {
                                            if(e.key === 'Enter' && !e.shiftKey) {
                                                e.preventDefault();
                                                handleSend();
                                            }
                                        }}
                                    />
                                    <button className="win-button w-24 font-bold text-lg" onClick={handleSend}>鍙戦€?/button>
                                </div>
                            </div>
                        </div>

                        {/* Right Sidebar: Settings + Agents Accordion */}
                        <div className={`outset flex flex-col h-full bg-panel transition-all duration-200 ${isAnyRightOpen ? 'w-80' : 'w-10'}`} style={{borderTop: 'none'}}>
                            
                            {/* --- Personal Settings Section --- */}
                            <div 
                                className={`sidebar-title cursor-pointer select-none border-b border-panel-dark ${!isAnyRightOpen ? 'flex-1 justify-center' : ''}`} 
                                onClick={() => { setIsSettingsOpen(!isSettingsOpen); if(!isSettingsOpen) setIsAgentOpen(false); }}
                            >
                                {isAnyRightOpen ? (
                                    <>
                                        <span>涓汉璁剧疆 鈿?/span>
                                        <span>{isSettingsOpen ? '[-]' : '[+]'}</span>
                                    </>
                                ) : (
                                    <span className="vertical-text">涓汉璁剧疆鈿?/span>
                                )}
                            </div>
                            
                            {isSettingsOpen && (
                                <div className="p-3 overflow-y-auto max-h-[50%] bg-inner flex-1 border-b border-panel-dark">
                                    <div className="flex justify-between items-center mb-3">
                                        <span className="font-bold">API 閰嶇疆鍒楄〃</span>
                                        <button className="win-button text-xs py-0" onClick={handleAddProfile}>+ 娣诲姞</button>
                                    </div>
                                    {profiles.map((p) => {
                                        const modelState = profileModelState[p.id] || {};
                                        const modelOptions = getProfileModelOptions(p.id, p.model);
                                        const canLoadModels = Boolean(String(p.apiKey || '').trim());

                                        return (
                                            <div key={p.id} className="inset p-2 mb-4 flex flex-col gap-2">
                                                <div className="flex gap-1 items-center">
                                                    <input
                                                        className="flex-1 font-bold"
                                                        value={p.name}
                                                        onChange={e => updateProfile(p.id, { name: e.target.value })}
                                                        placeholder="Profile Name"
                                                    />
                                                    <button
                                                        className="win-button px-2 py-1 text-red-600 font-bold leading-none"
                                                        title="Delete profile"
                                                        onClick={() => requestDeleteProfile(p.id)}
                                                    >
                                                        脳
                                                    </button>
                                                </div>
                                                <select
                                                    className="w-full"
                                                    value={p.provider}
                                                    onChange={e => updateProfile(p.id, { provider: e.target.value, model: '' })}
                                                >
                                                    {providerOptions.map((option) => (
                                                        <option key={option} value={option}>{option}</option>
                                                    ))}
                                                </select>
                                                <input
                                                    className="w-full"
                                                    value={p.baseUrl}
                                                    onChange={e => updateProfile(p.id, { baseUrl: e.target.value, model: '' })}
                                                    placeholder="Base URL (optional if provider has a default)"
                                                />
                                                <input
                                                    className="w-full"
                                                    value={p.apiKey}
                                                    onChange={e => updateProfile(p.id, { apiKey: e.target.value, model: '' })}
                                                    placeholder="API Key"
                                                    type="password"
                                                />
                                                <div className="flex gap-2 items-center">
                                                    <select
                                                        className="w-full"
                                                        value={p.model || ''}
                                                        onChange={e => updateProfile(p.id, { model: e.target.value })}
                                                        disabled={!canLoadModels || modelState.loading || modelOptions.length === 0}
                                                    >
                                                        {!canLoadModels && <option value="">Enter API Key to load models</option>}
                                                        {canLoadModels && modelState.loading && modelOptions.length === 0 && <option value="">Loading models...</option>}
                                                        {canLoadModels && !modelState.loading && modelOptions.length === 0 && <option value="">{modelState.error ? 'Failed to load models' : 'No models available'}</option>}
                                                        {modelOptions.map((model) => (
                                                            <option key={model} value={model}>{model}</option>
                                                        ))}
                                                    </select>
                                                    <button
                                                        className="win-button text-xs px-2 py-1"
                                                        onClick={() => refreshModelsForProfile(p)}
                                                        disabled={!canLoadModels || modelState.loading}
                                                        title="Refresh models"
                                                    >
                                                        {modelState.loading ? '...' : 'Refresh'}
                                                    </button>
                                                </div>
                                                {modelState.error && (
                                                    <div className="text-[11px] text-red-700 break-all">{modelState.error}</div>
                                                )}
                                            </div>
                                        );
                                    })}
                                    <div className="mt-4 pt-4 border-t border-panel-dark">
                                        <div className="font-bold mb-3 text-[14px]">AGENT 缁戝畾</div>
                                        {agents.map(a => (
                                            <div key={a.id} className="flex justify-between items-center text-[14px] mb-3">
                                                <span className="truncate w-1/2">{a.name}</span>
                                                <select className="h-7 w-32 px-1">
                                                    <option>Auto</option>
                                                    {profiles.map(p => <option key={p.id}>{p.name}</option>)}
                                                </select>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* --- Agent Console Section --- */}
                            <div 
                                className={`sidebar-title cursor-pointer select-none ${!isAnyRightOpen ? 'flex-1 justify-center' : ''}`} 
                                onClick={() => { setIsAgentOpen(!isAgentOpen); if(!isAgentOpen) setIsSettingsOpen(false); }}
                            >
                                {isAnyRightOpen ? (
                                    <>
                                        <span>AGENT 鎺у埗鍙?/span>
                                        <span>{isAgentOpen ? '[-]' : '[+]'}</span>
                                    </>
                                ) : (
                                    <span className="vertical-text">AGENT鎺у埗鍙?/span>
                                )}
                            </div>

                            {isAgentOpen && (
                                <div className="flex-1 overflow-y-auto p-2 bg-panel flex flex-col gap-1">
                                    {agents.map(a => (
                                        <div key={a.id} className="agent-card">
                                            <div className="flex items-center gap-2">
                                                <input type="checkbox" checked={a.enabled} onChange={() => setAgents(agents.map(x => x.id === a.id ? {...x, enabled: !x.enabled} : x))} />
                                                <span className="font-bold text-sm uppercase">{a.name}</span>
                                            </div>
                                            <div className="text-xs text-muted mt-1 line-clamp-2">{a.desc}</div>
                                            <div className="agent-actions">
                                                {!a.isDefault && (
                                                    <>
                                                        <button className="win-button text-[10px] p-0 px-1" onClick={() => setEditingAgent(a)}>鏀?/button>
                                                        <button className="win-button text-[10px] p-0 px-1 text-red-700 font-bold" onClick={() => requestDeleteAgent(a.id)}>鍒?/button>
                                                    </>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                    <button 
                                        className="win-button w-full mt-2 py-2 font-bold bg-inner"
                                        onClick={(e) => { e.stopPropagation(); handleAddAgent(); }}
                                        title="褰撳墠鐗堟湰鍥哄畾涓哄叚閮ㄩ棬鏋舵瀯"
                                    >
                                        鍏儴闂ㄥ浐瀹氭灦鏋?
                                    </button>
                                </div>
                            )}

                        </div>
                    </div>

                    {/* Confirm Modal */}
                    {confirmState.open && (
                        <div className="modal-overlay">
                            <div className="outset w-[320px] p-4 flex flex-col gap-3">
                                <div className="sidebar-title" style={{margin: '-4px -4px 10px -4px'}}>纭鎿嶄綔</div>
                                <div>{confirmState.message}</div>
                                <div className="flex justify-end gap-2 mt-2">
                                    <button className="win-button font-bold" onClick={executeConfirm}>纭畾</button>
                                    <button className="win-button" onClick={closeConfirm}>鍙栨秷</button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Rename Session Modal */}
                    {renamingSessionId && (
                        <div className="modal-overlay">
                            <div className="outset w-[300px] p-4 flex flex-col gap-3">
                                <div className="sidebar-title" style={{margin: '-4px -4px 10px -4px'}}>閲嶅懡鍚嶄細璇濇憳瑕?/div>
                                <input 
                                    className="w-full" 
                                    value={renameInput} 
                                    onChange={e => setRenameInput(e.target.value)} 
                                    autoFocus
                                    onKeyDown={e => { if(e.key === 'Enter') handleRenameSave(); }}
                                />
                                <div className="flex justify-end gap-2 mt-2">
                                    <button className="win-button font-bold" onClick={handleRenameSave}>纭畾</button>
                                    <button className="win-button" onClick={() => setRenamingSessionId(null)}>鍙栨秷</button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Agent Edit Modal */}
                    {editingAgent && (
                        <div className="modal-overlay">
                            <div className="outset w-[500px] p-4 flex flex-col gap-3">
                                <div className="sidebar-title" style={{margin: '-4px -4px 10px -4px'}}>缂栬緫 Agent 閰嶇疆</div>
                                <div>
                                    <label className="block text-xs font-bold mb-1">鍚嶇О</label>
                                    <input className="w-full" value={editingAgent.name} onChange={e => setEditingAgent({...editingAgent, name: e.target.value})} />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold mb-1">绠€浠?(Description)</label>
                                    <input className="w-full" value={editingAgent.desc} onChange={e => setEditingAgent({...editingAgent, desc: e.target.value})} />
                                </div>
                                <div>
                                    <label className="block text-xs font-bold mb-1">鑷畾涔夎亴璐?(Instructions / agent.md)</label>
                                    <textarea className="w-full h-40 font-mono text-xs" value={editingAgent.instructions} onChange={e => setEditingAgent({...editingAgent, instructions: e.target.value})} />
                                </div>
                                <div className="flex justify-end gap-2 mt-2">
                                    <button className="win-button font-bold" onClick={() => handleSaveAgent(editingAgent)}>淇濆瓨骞跺悓姝?/button>
                                    <button className="win-button" onClick={() => setEditingAgent(null)}>鍙栨秷</button>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            );
        };

        const root = ReactDOM.createRoot(document.getElementById('root'));
        root.render(<App />);
    