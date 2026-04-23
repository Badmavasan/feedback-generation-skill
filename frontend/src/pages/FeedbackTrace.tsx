import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, CheckCircle, XCircle, Clock, ChevronDown, ChevronUp, Code } from 'lucide-react'
import { getHistoryRecord } from '../api/client'
import type { FeedbackRecordDetail, AgentLog } from '../types'

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('fr-FR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${color}`}>{text}</span>
  )
}

const AGENT_COLORS: Record<string, string> = {
  orchestrator: 'bg-purple-100 text-purple-700',
  generator: 'bg-blue-100 text-blue-700',
  relevance_checker: 'bg-yellow-100 text-yellow-700',
  student_simulator: 'bg-green-100 text-green-700',
  coherence: 'bg-orange-100 text-orange-700',
}

const VERDICT_COLORS: Record<string, string> = {
  ACCEPTED: 'bg-green-100 text-green-700',
  REJECTED: 'bg-red-100 text-red-700',
  RELEVANT: 'bg-green-100 text-green-700',
  IRRELEVANT: 'bg-red-100 text-red-700',
  PASS: 'bg-green-100 text-green-700',
  FAIL: 'bg-red-100 text-red-700',
}

function JsonBlock({ data }: { data: unknown }) {
  const [open, setOpen] = useState(false)
  if (data === null || data === undefined) return <span className="text-gray-400 text-xs">—</span>
  const preview = typeof data === 'string' ? data.slice(0, 120) : JSON.stringify(data).slice(0, 120)
  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 text-xs text-indigo-600 hover:underline"
      >
        <Code size={12} />{open ? 'Masquer' : 'Voir les données'}
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
      </button>
      {!open && <p className="text-xs text-gray-400 font-mono truncate mt-0.5">{preview}…</p>}
      {open && (
        <pre className="mt-2 p-3 bg-gray-900 text-green-300 text-xs rounded-lg overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap break-all">
          {typeof data === 'string' ? data : JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  )
}

function LogRow({ log }: { log: AgentLog }) {
  const [open, setOpen] = useState(false)
  const agentColor = AGENT_COLORS[log.agent] ?? 'bg-gray-100 text-gray-700'
  const verdictColor = log.verdict ? VERDICT_COLORS[log.verdict] ?? 'bg-gray-100 text-gray-600' : ''

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-white hover:bg-gray-50 text-left"
      >
        <span className="text-xs font-mono text-gray-400 w-6 shrink-0">#{log.step_number}</span>
        <Badge text={log.agent} color={agentColor} />
        <span className="text-xs text-gray-600 font-medium flex-1">{log.role}</span>
        {log.tool_name && <Badge text={log.tool_name} color="bg-gray-100 text-gray-600" />}
        {log.characteristic && <Badge text={log.characteristic} color="bg-indigo-50 text-indigo-700" />}
        {log.attempt !== null && <span className="text-xs text-gray-400">try {log.attempt}</span>}
        {log.verdict && <Badge text={log.verdict} color={verdictColor} />}
        {log.duration_ms !== null && (
          <span className="text-xs text-gray-400 font-mono">{log.duration_ms}ms</span>
        )}
        {open ? <ChevronUp size={14} className="text-gray-400 shrink-0" /> : <ChevronDown size={14} className="text-gray-400 shrink-0" />}
      </button>

      {open && (
        <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 space-y-3">
          {log.notes && (
            <p className="text-xs text-gray-600 bg-white border border-gray-200 rounded p-2 font-mono whitespace-pre-wrap">
              {log.notes}
            </p>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1">Input</p>
              <JsonBlock data={log.input_data} />
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 mb-1">Output</p>
              <JsonBlock data={log.output_data} />
            </div>
          </div>
          <p className="text-xs text-gray-400">{formatDate(log.created_at)}</p>
        </div>
      )}
    </div>
  )
}

export default function FeedbackTrace() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [record, setRecord] = useState<FeedbackRecordDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [xmlOpen, setXmlOpen] = useState(false)

  useEffect(() => {
    if (!id) return
    getHistoryRecord(id)
      .then(r => setRecord(r.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className="text-center py-16 text-gray-400">Chargement…</div>
  if (!record) return <div className="text-center py-16 text-gray-400">Introuvable</div>

  const statusIcon = record.status === 'completed'
    ? <CheckCircle size={16} className="text-green-500" />
    : record.status === 'failed'
    ? <XCircle size={16} className="text-red-500" />
    : <Clock size={16} className="text-yellow-500" />

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Back */}
      <button
        onClick={() => navigate('/history')}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800"
      >
        <ArrowLeft size={14} />Retour à l'historique
      </button>

      {/* Header card */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              {statusIcon}
              <h1 className="text-lg font-semibold text-gray-900 font-mono">{record.kc_name}</h1>
            </div>
            <p className="text-sm text-gray-500">{record.kc_description}</p>
          </div>
          <div className="text-right text-xs text-gray-400">
            <p className="font-mono">{record.id}</p>
            <p>{formatDate(record.created_at)}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          <div className="bg-gray-50 rounded p-2.5">
            <p className="text-gray-400 uppercase tracking-wide font-semibold mb-0.5">Platform</p>
            <p className="font-mono text-indigo-700 font-medium">{record.platform_id}</p>
          </div>
          <div className="bg-gray-50 rounded p-2.5">
            <p className="text-gray-400 uppercase tracking-wide font-semibold mb-0.5">Mode</p>
            <p className="font-mono text-gray-800">{record.mode} / {record.level}</p>
          </div>
          <div className="bg-gray-50 rounded p-2.5">
            <p className="text-gray-400 uppercase tracking-wide font-semibold mb-0.5">Exercice</p>
            <p className="font-mono text-gray-800">{record.exercise_id ?? '—'}</p>
          </div>
          <div className="bg-gray-50 rounded p-2.5">
            <p className="text-gray-400 uppercase tracking-wide font-semibold mb-0.5">Itérations</p>
            <p className="font-mono text-gray-800">{record.total_iterations ?? '—'}</p>
          </div>
        </div>

        <div>
          <p className="text-xs text-gray-400 uppercase tracking-wide font-semibold mb-1.5">Caractéristiques</p>
          <div className="flex flex-wrap gap-1.5">
            {record.characteristics.map(c => (
              <span key={c} className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded font-medium">{c}</span>
            ))}
          </div>
        </div>

        {record.error_message && (
          <div className="bg-red-50 border border-red-200 rounded p-3">
            <p className="text-xs text-red-700 font-medium mb-0.5">Erreur</p>
            <p className="text-xs text-red-600 font-mono">{record.error_message}</p>
          </div>
        )}
      </div>

      {/* Result XML */}
      {record.result_xml && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <button
            onClick={() => setXmlOpen(o => !o)}
            className="w-full flex items-center justify-between px-5 py-3 hover:bg-gray-50 text-left"
          >
            <span className="text-sm font-semibold text-gray-700">Résultat XML</span>
            {xmlOpen ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
          </button>
          {xmlOpen && (
            <div className="border-t border-gray-200">
              <pre className="p-4 bg-gray-900 text-green-300 text-xs overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto">
                {record.result_xml}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Agent logs */}
      <div>
        <h2 className="text-base font-semibold text-gray-800 mb-3">
          Trace agent ({record.logs.length} étape{record.logs.length !== 1 ? 's' : ''})
        </h2>
        <div className="space-y-2">
          {record.logs.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-8">Aucun log enregistré</p>
          )}
          {record.logs
            .slice()
            .sort((a, b) => a.step_number - b.step_number)
            .map(log => (
              <LogRow key={log.id} log={log} />
            ))}
        </div>
      </div>
    </div>
  )
}
