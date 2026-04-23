import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Globe, Sparkles, ArrowRight, Database, History } from 'lucide-react'
import { listPlatforms, listHistory } from '../api/client'
import type { Platform, FeedbackRecord } from '../types'

function StatCard({
  label,
  value,
  sub,
  delay,
}: {
  label: string
  value: string | number
  sub?: string
  delay: string
}) {
  return (
    <div
      className={`rounded-xl p-5 border relative overflow-hidden animate-fade-up stagger-${delay}`}
      style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
    >
      <p
        className="text-xs font-display font-medium uppercase tracking-widest mb-2"
        style={{ color: 'var(--text-muted)' }}
      >
        {label}
      </p>
      <p
        className="font-display text-3xl font-bold"
        style={{ color: 'var(--text-primary)' }}
      >
        {value}
      </p>
      {sub && (
        <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
          {sub}
        </p>
      )}
      {/* Decorative corner accent */}
      <div
        className="absolute -bottom-4 -right-4 w-20 h-20 rounded-full opacity-10"
        style={{ background: 'var(--accent)' }}
      />
    </div>
  )
}

export default function Dashboard() {
  const [platforms, setPlatforms] = useState<Platform[]>([])
  const [recentHistory, setRecentHistory] = useState<FeedbackRecord[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      listPlatforms().then(r => setPlatforms(r.data)),
      listHistory(undefined, 5, 0).then(r => setRecentHistory(r.data)),
    ])
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const totalChunks = platforms.reduce((s, p) => s + p.context_chunk_count, 0)

  return (
    <div>
      {/* Header */}
      <div className="mb-8 animate-fade-up">
        <h1
          className="font-display text-2xl font-bold mb-1"
          style={{ color: 'var(--text-primary)' }}
        >
          Dashboard
        </h1>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          Multi-platform · Multi-agent · Pedagogical feedback
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <StatCard
          label="Platforms"
          value={loading ? '—' : platforms.length}
          sub="registered"
          delay="1"
        />
        <StatCard
          label="Context chunks"
          value={loading ? '—' : totalChunks}
          sub="embedded across all platforms"
          delay="2"
        />
        <StatCard label="Agents" value="3" sub="Claude · Mistral · Gemini" delay="3" />
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        {[
          { to: '/generate', label: 'Générer du feedback', sub: 'Offline mode · XML output', icon: Sparkles, bg: 'rgba(245,158,11,0.12)', color: 'var(--amber)' },
          { to: '/history', label: 'Historique', sub: 'Toutes les générations', icon: History, bg: 'rgba(99,102,241,0.12)', color: 'var(--accent)' },
          { to: '/platforms', label: 'Platforms', sub: 'Créer, éditer, contexte', icon: Globe, bg: 'rgba(99,102,241,0.12)', color: 'var(--accent)' },
        ].map(({ to, label, sub, icon: Icon, bg, color }, i) => (
          <Link
            key={to}
            to={to}
            className={`group rounded-xl p-5 border flex items-center justify-between transition-all duration-150 animate-fade-up stagger-${i + 1}`}
            style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.borderColor = 'var(--border-hover)')}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.borderColor = 'var(--border)')}
          >
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: bg }}>
                <Icon size={16} style={{ color }} />
              </div>
              <div>
                <p className="font-display font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>{label}</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{sub}</p>
              </div>
            </div>
            <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" style={{ color: 'var(--text-muted)' }} />
          </Link>
        ))}
      </div>

      {/* Recent generations */}
      {!loading && recentHistory.length > 0 && (
        <div
          className="rounded-xl border overflow-hidden animate-fade-up stagger-5 mb-6"
          style={{ borderColor: 'var(--border)' }}
        >
          <div
            className="px-5 py-3 border-b flex items-center justify-between"
            style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
          >
            <div className="flex items-center gap-2">
              <History size={13} style={{ color: 'var(--text-muted)' }} />
              <span className="text-xs font-display font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
                Générations récentes
              </span>
            </div>
            <Link to="/history" className="text-xs" style={{ color: 'var(--accent)' }}>Voir tout →</Link>
          </div>
          {recentHistory.map((r, i) => (
            <Link
              key={r.id}
              to={`/history/${r.id}`}
              className="flex items-center justify-between px-5 py-3 border-b last:border-0 hover:bg-[var(--bg-elevated)] transition-colors"
              style={{ background: i % 2 === 0 ? 'var(--bg-surface)' : 'var(--bg-elevated)', borderColor: 'var(--border)' }}
            >
              <div className="flex items-center gap-3">
                {r.status === 'completed'
                  ? <div className="w-2 h-2 rounded-full bg-green-400" />
                  : r.status === 'failed'
                  ? <div className="w-2 h-2 rounded-full bg-red-400" />
                  : <div className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse-dot" />}
                <span className="font-mono text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{r.kc_name}</span>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>{r.exercise_id ?? ''}</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex gap-1">
                  {r.characteristics.slice(0, 2).map(c => (
                    <span key={c} className="text-xs px-1.5 py-0.5 rounded" style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--accent)' }}>{c}</span>
                  ))}
                </div>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {new Date(r.created_at).toLocaleDateString('fr-FR')}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Platform list preview */}
      {!loading && platforms.length > 0 && (
        <div
          className="rounded-xl border overflow-hidden animate-fade-up stagger-5"
          style={{ borderColor: 'var(--border)' }}
        >
          <div
            className="px-5 py-3 border-b flex items-center gap-2"
            style={{
              background: 'var(--bg-surface)',
              borderColor: 'var(--border)',
            }}
          >
            <Database size={13} style={{ color: 'var(--text-muted)' }} />
            <span
              className="text-xs font-display font-semibold uppercase tracking-widest"
              style={{ color: 'var(--text-muted)' }}
            >
              Registered platforms
            </span>
          </div>
          {platforms.map((p, i) => (
            <div
              key={p.id}
              className="px-5 py-3 flex items-center justify-between border-b last:border-0"
              style={{
                background: i % 2 === 0 ? 'var(--bg-surface)' : 'var(--bg-elevated)',
                borderColor: 'var(--border)',
              }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-2 h-2 rounded-full animate-pulse-dot"
                  style={{ background: 'var(--accent)' }}
                />
                <span
                  className="font-mono text-sm font-medium"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {p.id}
                </span>
                <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  {p.name}
                </span>
              </div>
              <div className="flex items-center gap-4">
                <span
                  className="text-xs font-mono px-2 py-0.5 rounded"
                  style={{
                    background: 'rgba(99,102,241,0.1)',
                    color: 'var(--accent)',
                  }}
                >
                  {p.language.toUpperCase()}
                </span>
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {p.context_chunk_count} chunks
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
