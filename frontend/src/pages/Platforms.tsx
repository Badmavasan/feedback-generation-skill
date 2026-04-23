import { useEffect, useState, useCallback } from 'react'
import { Plus, Trash2, ChevronDown, ChevronUp, X, Save, Settings, CheckCircle, Circle } from 'lucide-react'
import {
  listPlatforms,
  createPlatform,
  updatePlatform,
  deletePlatform,
  getGeneralConfig,
  updateGeneralConfig,
  listPlatformConfigs,
  createPlatformConfig,
  updatePlatformConfig,
  deletePlatformConfig,
  activatePlatformConfig,
} from '../api/client'
import type { Platform, PlatformUpdate, PlatformConfig } from '../types'

// ── General config panel ──────────────────────────────────────────────────────

function GeneralConfigPanel() {
  const [instructions, setInstructions] = useState('')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<'idle' | 'saved' | 'error'>('idle')

  useEffect(() => {
    getGeneralConfig()
      .then(r => setInstructions(r.data.general_feedback_instructions))
      .catch(console.error)
  }, [])

  const handleSave = async () => {
    setSaving(true)
    setStatus('idle')
    try {
      await updateGeneralConfig({ general_feedback_instructions: instructions })
      setStatus('saved')
      setTimeout(() => setStatus('idle'), 2000)
    } catch {
      setStatus('error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className="rounded-xl border p-5 mb-8 animate-fade-up"
      style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Settings size={14} style={{ color: 'var(--text-muted)' }} />
          <span
            className="text-xs font-display font-semibold uppercase tracking-widest"
            style={{ color: 'var(--text-muted)' }}
          >
            General feedback instructions
          </span>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-display font-semibold disabled:opacity-50 transition-all"
          style={{ background: 'var(--accent)', color: '#fff' }}
        >
          <Save size={12} />
          {saving ? 'Saving…' : 'Save'}
          {status === 'saved' && ' ✓'}
        </button>
      </div>
      <p className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>
        These instructions are injected into every generation prompt, regardless of platform.
      </p>
      <textarea
        value={instructions}
        onChange={e => setInstructions(e.target.value)}
        rows={6}
        placeholder="Enter global feedback instructions…"
        className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
        style={{
          background: 'var(--bg-elevated)',
          borderColor: 'var(--border)',
          color: 'var(--text-primary)',
        }}
        onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
        onBlur={e => (e.target.style.borderColor = 'var(--border)')}
      />
      {status === 'error' && (
        <p className="text-xs text-red-400 font-mono mt-2">Save failed</p>
      )}
    </div>
  )
}

// ── Platform row ──────────────────────────────────────────────────────────────

function PlatformRow({
  platform,
  onDelete,
  onUpdated,
}: {
  platform: Platform
  onDelete: () => void
  onUpdated: (p: Platform) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [tab, setTab] = useState<'settings' | 'configs'>('settings')

  // Configurations tab state
  const [configs, setConfigs] = useState<PlatformConfig[]>([])
  const [configsLoaded, setConfigsLoaded] = useState(false)
  const [editingConfig, setEditingConfig] = useState<PlatformConfig | null>(null)
  const [newConfigForm, setNewConfigForm] = useState({ name: '', vocabulary_to_use: '', vocabulary_to_avoid: '', teacher_comments: '' })
  const [showNewConfig, setShowNewConfig] = useState(false)
  const [configSaving, setConfigSaving] = useState(false)

  // Settings tab state
  const [form, setForm] = useState<PlatformUpdate>({
    name: platform.name,
    language: platform.language,
    description: platform.description,
    feedback_mode: platform.feedback_mode,
    platform_context: platform.platform_context ?? '',
    live_student_prompt: platform.live_student_prompt ?? '',
  })
  const [savingSettings, setSavingSettings] = useState(false)
  const [settingsStatus, setSettingsStatus] = useState<'idle' | 'saved' | 'error'>('idle')


  const loadConfigs = useCallback(async () => {
    const res = await listPlatformConfigs(platform.id)
    setConfigs(res.data)
    setConfigsLoaded(true)
  }, [platform.id])

  useEffect(() => {
    if (tab === 'configs' && !configsLoaded) loadConfigs()
  }, [tab, configsLoaded, loadConfigs])

  const handleCreateConfig = async () => {
    if (!newConfigForm.name.trim()) return
    setConfigSaving(true)
    try {
      await createPlatformConfig(platform.id, {
        name: newConfigForm.name,
        vocabulary_to_use: newConfigForm.vocabulary_to_use || null,
        vocabulary_to_avoid: newConfigForm.vocabulary_to_avoid || null,
        teacher_comments: newConfigForm.teacher_comments || null,
      })
      setShowNewConfig(false)
      setNewConfigForm({ name: '', vocabulary_to_use: '', vocabulary_to_avoid: '', teacher_comments: '' })
      await loadConfigs()
    } finally {
      setConfigSaving(false)
    }
  }

  const handleUpdateConfig = async (cfg: PlatformConfig) => {
    setConfigSaving(true)
    try {
      await updatePlatformConfig(platform.id, cfg.id, {
        name: cfg.name,
        vocabulary_to_use: cfg.vocabulary_to_use,
        vocabulary_to_avoid: cfg.vocabulary_to_avoid,
        teacher_comments: cfg.teacher_comments,
      })
      setEditingConfig(null)
      await loadConfigs()
    } finally {
      setConfigSaving(false)
    }
  }

  const handleActivateConfig = async (configId: number) => {
    await activatePlatformConfig(platform.id, configId)
    await loadConfigs()
  }

  const handleDeleteConfig = async (configId: number) => {
    if (!confirm('Delete this configuration?')) return
    await deletePlatformConfig(platform.id, configId)
    await loadConfigs()
  }

  const handleSaveSettings = async () => {
    setSavingSettings(true)
    setSettingsStatus('idle')
    try {
      const res = await updatePlatform(platform.id, form)
      onUpdated(res.data)
      setSettingsStatus('saved')
      setTimeout(() => setSettingsStatus('idle'), 2000)
    } catch {
      setSettingsStatus('error')
    } finally {
      setSavingSettings(false)
    }
  }

  return (
    <div
      className="rounded-xl border overflow-hidden transition-all"
      style={{ borderColor: expanded ? 'var(--border-hover)' : 'var(--border)' }}
    >
      {/* Row header */}
      <div
        className="px-5 py-4 flex items-center justify-between cursor-pointer"
        style={{ background: 'var(--bg-surface)' }}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-4">
          <div className="w-2 h-2 rounded-full" style={{ background: 'var(--accent)' }} />
          <div>
            <span className="font-display font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
              {platform.name}
            </span>
            <span className="font-mono text-xs ml-2" style={{ color: 'var(--text-muted)' }}>
              [{platform.id}]
            </span>
          </div>
          <span
            className="text-xs font-mono px-2 py-0.5 rounded"
            style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--accent)' }}
          >
            {platform.language.toUpperCase()}
          </span>
          <span
            className="text-xs font-mono px-2 py-0.5 rounded"
            style={{
              background: platform.feedback_mode === 'live' ? 'rgba(52,211,153,0.1)' : 'rgba(245,158,11,0.1)',
              color: platform.feedback_mode === 'live' ? '#34d399' : 'var(--amber)',
            }}
          >
            {platform.feedback_mode}
          </span>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {platform.context_chunk_count} chunks
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={e => {
              e.stopPropagation()
              if (confirm(`Delete platform "${platform.id}"?`)) onDelete()
            }}
            className="p-1.5 rounded-lg transition-colors hover:bg-red-500/10"
            style={{ color: 'var(--text-muted)' }}
          >
            <Trash2 size={13} />
          </button>
          {expanded
            ? <ChevronUp size={14} style={{ color: 'var(--text-muted)' }} />
            : <ChevronDown size={14} style={{ color: 'var(--text-muted)' }} />}
        </div>
      </div>

      {/* Expanded panel */}
      {expanded && (
        <div
          className="border-t"
          style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)' }}
        >
          {/* Tabs */}
          <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>
            {(['settings', 'configs'] as const).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className="px-5 py-2.5 text-xs font-display font-semibold uppercase tracking-widest transition-colors flex items-center gap-1.5"
                style={{
                  color: tab === t ? 'var(--accent)' : 'var(--text-muted)',
                  borderBottom: tab === t ? '2px solid var(--accent)' : '2px solid transparent',
                }}
              >
                {t === 'settings' ? 'Settings' : (
                  <>
                    Configurations
                    {configs.some(c => c.is_active) && (
                      <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
                    )}
                  </>
                )}
              </button>
            ))}
          </div>

          {/* Settings tab */}
          {tab === 'settings' && (
            <div className="px-5 py-4 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                    Name
                  </label>
                  <input
                    value={form.name ?? ''}
                    onChange={e => setForm({ ...form, name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none font-mono"
                    style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                    onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
                    onBlur={e => (e.target.style.borderColor = 'var(--border)')}
                  />
                </div>
                <div>
                  <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                    Language
                  </label>
                  <select
                    value={form.language ?? 'fr'}
                    onChange={e => setForm({ ...form, language: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none font-mono"
                    style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  >
                    <option value="fr">French (fr)</option>
                    <option value="en">English (en)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                    Feedback mode
                  </label>
                  <select
                    value={form.feedback_mode ?? 'offline'}
                    onChange={e => setForm({ ...form, feedback_mode: e.target.value as 'offline' | 'live' })}
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none font-mono"
                    style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  >
                    <option value="offline">Offline — reusable feedback</option>
                    <option value="live">Live — includes student submission</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                    Description
                  </label>
                  <input
                    value={form.description ?? ''}
                    onChange={e => setForm({ ...form, description: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none font-mono"
                    style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                    onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
                    onBlur={e => (e.target.style.borderColor = 'var(--border)')}
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                  Platform context
                  <span className="ml-1 normal-case font-normal" style={{ color: 'var(--text-muted)' }}>
                    — pedagogical guidelines, tone, audience (injected in every prompt)
                  </span>
                </label>
                <textarea
                  value={form.platform_context ?? ''}
                  onChange={e => setForm({ ...form, platform_context: e.target.value })}
                  rows={8}
                  placeholder="Enter platform-specific context: target audience, pedagogical approach, tone guidelines…"
                  className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
                  style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
                  onBlur={e => (e.target.style.borderColor = 'var(--border)')}
                />
              </div>

              {form.feedback_mode === 'live' && (
                <div>
                  <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                    Live student prompt
                    <span className="ml-1 normal-case font-normal" style={{ color: '#34d399' }}>
                      — only for live mode
                    </span>
                  </label>
                  <textarea
                    value={form.live_student_prompt ?? ''}
                    onChange={e => setForm({ ...form, live_student_prompt: e.target.value })}
                    rows={5}
                    placeholder="Additional instructions for live mode — how to interpret and use the student's submitted code…"
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
                    style={{ background: 'var(--bg-surface)', borderColor: 'rgba(52,211,153,0.3)', color: 'var(--text-primary)' }}
                    onFocus={e => (e.target.style.borderColor = '#34d399')}
                    onBlur={e => (e.target.style.borderColor = 'rgba(52,211,153,0.3)')}
                  />
                </div>
              )}

              <div className="flex items-center justify-between pt-1">
                {settingsStatus === 'saved' && (
                  <span className="text-xs font-mono text-green-400">Saved ✓</span>
                )}
                {settingsStatus === 'error' && (
                  <span className="text-xs font-mono text-red-400">Save failed</span>
                )}
                <div className="ml-auto">
                  <button
                    onClick={handleSaveSettings}
                    disabled={savingSettings}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-display font-semibold disabled:opacity-50 transition-all"
                    style={{ background: 'var(--accent)', color: '#fff' }}
                  >
                    <Save size={13} />
                    {savingSettings ? 'Saving…' : 'Save settings'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Configurations tab */}
          {tab === 'configs' && (
            <div className="px-5 py-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  Named configurations with vocabulary rules and teacher comments. The active configuration is injected into every generation prompt as the 7th quality dimension.
                </p>
                <button
                  onClick={() => setShowNewConfig(!showNewConfig)}
                  className="ml-4 shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-display font-semibold transition-all"
                  style={{ background: 'var(--accent)', color: '#fff' }}
                >
                  {showNewConfig ? <X size={11} /> : <Plus size={11} />}
                  {showNewConfig ? 'Cancel' : 'New config'}
                </button>
              </div>

              {showNewConfig && (
                <div className="rounded-lg border p-4 space-y-3" style={{ borderColor: 'var(--border-hover)', background: 'var(--bg-surface)' }}>
                  <p className="text-xs font-display font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>New configuration</p>
                  <input
                    placeholder="Configuration name *"
                    value={newConfigForm.name}
                    onChange={e => setNewConfigForm({ ...newConfigForm, name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none font-mono"
                    style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  />
                  <textarea rows={3} placeholder="Vocabulary to use — style, preferred expressions…"
                    value={newConfigForm.vocabulary_to_use}
                    onChange={e => setNewConfigForm({ ...newConfigForm, vocabulary_to_use: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
                    style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  />
                  <textarea rows={3} placeholder="Vocabulary to avoid — forbidden words, one per line or comma-separated"
                    value={newConfigForm.vocabulary_to_avoid}
                    onChange={e => setNewConfigForm({ ...newConfigForm, vocabulary_to_avoid: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
                    style={{ background: 'var(--bg-elevated)', borderColor: 'rgba(248,113,113,0.4)', color: 'var(--text-primary)' }}
                  />
                  <textarea rows={4} placeholder="Teacher comments — pedagogical priorities, platform-specific rules…"
                    value={newConfigForm.teacher_comments}
                    onChange={e => setNewConfigForm({ ...newConfigForm, teacher_comments: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
                    style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  />
                  <button onClick={handleCreateConfig} disabled={configSaving || !newConfigForm.name.trim()}
                    className="px-4 py-2 rounded-lg text-sm font-display font-semibold disabled:opacity-50"
                    style={{ background: 'var(--accent)', color: '#fff' }}>
                    {configSaving ? 'Creating…' : 'Create'}
                  </button>
                </div>
              )}

              {configs.length === 0 ? (
                <p className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>No configurations yet.</p>
              ) : (
                <div className="space-y-2">
                  {configs.map(cfg => (
                    <div key={cfg.id} className="rounded-lg border" style={{ borderColor: cfg.is_active ? 'rgba(52,211,153,0.4)' : 'var(--border)', background: 'var(--bg-surface)' }}>
                      {editingConfig?.id === cfg.id ? (
                        <div className="p-4 space-y-3">
                          <input value={editingConfig.name}
                            onChange={e => setEditingConfig({ ...editingConfig, name: e.target.value })}
                            className="w-full px-3 py-2 rounded-lg text-sm border outline-none font-mono"
                            style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                          />
                          <textarea rows={3} placeholder="Vocabulary to use"
                            value={editingConfig.vocabulary_to_use ?? ''}
                            onChange={e => setEditingConfig({ ...editingConfig, vocabulary_to_use: e.target.value || null })}
                            className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
                            style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                          />
                          <textarea rows={3} placeholder="Vocabulary to avoid"
                            value={editingConfig.vocabulary_to_avoid ?? ''}
                            onChange={e => setEditingConfig({ ...editingConfig, vocabulary_to_avoid: e.target.value || null })}
                            className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
                            style={{ background: 'var(--bg-elevated)', borderColor: 'rgba(248,113,113,0.4)', color: 'var(--text-primary)' }}
                          />
                          <textarea rows={4} placeholder="Teacher comments"
                            value={editingConfig.teacher_comments ?? ''}
                            onChange={e => setEditingConfig({ ...editingConfig, teacher_comments: e.target.value || null })}
                            className="w-full px-3 py-2 rounded-lg text-sm border outline-none resize-y font-mono"
                            style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                          />
                          <div className="flex gap-2">
                            <button onClick={() => handleUpdateConfig(editingConfig)} disabled={configSaving}
                              className="px-3 py-1.5 rounded-lg text-xs font-display font-semibold disabled:opacity-50"
                              style={{ background: 'var(--accent)', color: '#fff' }}>
                              {configSaving ? 'Saving…' : 'Save'}
                            </button>
                            <button onClick={() => setEditingConfig(null)}
                              className="px-3 py-1.5 rounded-lg text-xs font-display font-semibold"
                              style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div className="px-4 py-3 flex items-start justify-between gap-3">
                          <div className="flex items-start gap-3 min-w-0">
                            <button onClick={() => handleActivateConfig(cfg.id)} className="mt-0.5 shrink-0" title={cfg.is_active ? 'Active' : 'Activate'}>
                              {cfg.is_active
                                ? <CheckCircle size={15} className="text-green-400" />
                                : <Circle size={15} style={{ color: 'var(--text-muted)' }} />}
                            </button>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-display font-semibold" style={{ color: 'var(--text-primary)' }}>{cfg.name}</span>
                                {cfg.is_active && <span className="text-xs px-1.5 py-0.5 rounded font-mono" style={{ background: 'rgba(52,211,153,0.15)', color: '#34d399' }}>active</span>}
                              </div>
                              {cfg.vocabulary_to_avoid && (
                                <p className="text-xs mt-0.5 truncate" style={{ color: '#f87171' }}>
                                  Avoid: {cfg.vocabulary_to_avoid}
                                </p>
                              )}
                              {cfg.teacher_comments && (
                                <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>
                                  {cfg.teacher_comments}
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-1 shrink-0">
                            <button onClick={() => setEditingConfig({ ...cfg })}
                              className="p-1.5 rounded hover:bg-white/5 text-xs font-mono"
                              style={{ color: 'var(--text-muted)' }}>
                              Edit
                            </button>
                            <button onClick={() => handleDeleteConfig(cfg.id)}
                              className="p-1.5 rounded hover:bg-red-500/10"
                              style={{ color: 'var(--text-muted)' }}>
                              <Trash2 size={12} />
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Platforms() {
  const [platforms, setPlatforms] = useState<Platform[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({
    id: '', name: '', language: 'fr', description: '',
    feedback_mode: 'offline' as 'offline' | 'live',
    platform_context: '', live_student_prompt: '',
  })
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    listPlatforms()
      .then(r => setPlatforms(r.data))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    setCreateError('')
    try {
      await createPlatform(form)
      setShowCreate(false)
      setForm({ id: '', name: '', language: 'fr', description: '', feedback_mode: 'offline', platform_context: '', live_student_prompt: '' })
      load()
    } catch (e: any) {
      setCreateError(e.response?.data?.detail || 'Error creating platform')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deletePlatform(id)
      load()
    } catch (e) {
      console.error(e)
    }
  }

  const handleUpdated = (updated: Platform) => {
    setPlatforms(prev => prev.map(p => p.id === updated.id ? { ...p, ...updated } : p))
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6 animate-fade-up">
        <div>
          <h1 className="font-display text-2xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>
            Platforms
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Manage platform contexts, feedback mode, and global instructions
          </p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-display font-semibold transition-all"
          style={{ background: 'var(--accent)', color: '#fff' }}
        >
          {showCreate ? <X size={14} /> : <Plus size={14} />}
          {showCreate ? 'Cancel' : 'New platform'}
        </button>
      </div>

      {/* General config */}
      <GeneralConfigPanel />

      {/* Create form */}
      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="rounded-xl border p-5 mb-6 animate-fade-up"
          style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-hover)' }}
        >
          <p className="text-xs font-display font-semibold uppercase tracking-widest mb-4" style={{ color: 'var(--text-muted)' }}>
            New platform
          </p>
          <div className="grid grid-cols-2 gap-4">
            {(['id', 'name', 'description'] as const).map(field => (
              <div key={field} className={field === 'description' ? 'col-span-2' : ''}>
                <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                  {field}
                </label>
                <input
                  type="text"
                  value={form[field]}
                  onChange={e => setForm({ ...form, [field]: e.target.value })}
                  required={field !== 'description'}
                  placeholder={field === 'id' ? 'e.g. pyrates' : field === 'name' ? 'e.g. PyRates' : 'Short description'}
                  className="w-full px-3 py-2 rounded-lg text-sm font-mono border outline-none"
                  style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                  onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
                  onBlur={e => (e.target.style.borderColor = 'var(--border)')}
                />
              </div>
            ))}
            <div>
              <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                Language
              </label>
              <select
                value={form.language}
                onChange={e => setForm({ ...form, language: e.target.value })}
                className="w-full px-3 py-2 rounded-lg text-sm font-mono border outline-none"
                style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="fr">French (fr)</option>
                <option value="en">English (en)</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-display font-medium mb-1.5 uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                Feedback mode
              </label>
              <select
                value={form.feedback_mode}
                onChange={e => setForm({ ...form, feedback_mode: e.target.value as 'offline' | 'live' })}
                className="w-full px-3 py-2 rounded-lg text-sm font-mono border outline-none"
                style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
              >
                <option value="offline">Offline</option>
                <option value="live">Live</option>
              </select>
            </div>
          </div>
          {createError && <p className="text-xs text-red-400 font-mono mt-3">{createError}</p>}
          <button
            type="submit"
            disabled={creating}
            className="mt-4 px-5 py-2 rounded-lg text-sm font-display font-semibold disabled:opacity-50"
            style={{ background: 'var(--accent)', color: '#fff' }}
          >
            {creating ? 'Creating…' : 'Create platform'}
          </button>
        </form>
      )}

      {/* Platform list */}
      {loading ? (
        <div className="flex items-center gap-2 py-12 justify-center">
          <div
            className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
            style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }}
          />
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading…</span>
        </div>
      ) : platforms.length === 0 ? (
        <div className="rounded-xl border py-16 text-center" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>No platforms yet. Create one above.</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {platforms.map(p => (
            <PlatformRow
              key={p.id}
              platform={p}
              onDelete={() => handleDelete(p.id)}
              onUpdated={handleUpdated}
            />
          ))}
        </div>
      )}
    </div>
  )
}
