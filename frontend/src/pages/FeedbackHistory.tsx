import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, XCircle, Clock, ChevronRight, RefreshCw, Trash2 } from 'lucide-react'
import { listHistory, deleteHistoryRecord } from '../api/client'
import type { FeedbackRecord } from '../types'

const STATUS_ICON = {
  completed: <CheckCircle size={14} className="text-green-500" />,
  failed: <XCircle size={14} className="text-red-500" />,
  pending: <Clock size={14} className="text-yellow-500" />,
}

const STATUS_LABEL: Record<string, string> = {
  completed: 'Terminé',
  failed: 'Échoué',
  pending: 'En cours',
}

function formatDate(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

export default function FeedbackHistory() {
  const [records, setRecords] = useState<FeedbackRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [platform, setPlatform] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 25
  const navigate = useNavigate()

  const load = (p = platform, o = offset) => {
    setLoading(true)
    listHistory(p || undefined, limit, o)
      .then(r => setRecords(r.data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const applyFilter = () => { setOffset(0); load(platform, 0) }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (!confirm('Supprimer ce feedback ?')) return
    await deleteHistoryRecord(id)
    load()
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Historique des générations</h1>
        <button
          onClick={() => load()}
          className="flex items-center gap-2 border border-gray-300 text-gray-700 text-sm px-3 py-2 rounded-lg hover:bg-gray-50"
        >
          <RefreshCw size={14} />Rafraîchir
        </button>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <input
          value={platform}
          onChange={e => setPlatform(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && applyFilter()}
          placeholder="Filtrer par platform_id…"
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none w-56"
        />
        <button
          onClick={applyFilter}
          className="bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg"
        >
          Filtrer
        </button>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-x-auto">
        <table className="w-full text-sm min-w-[1000px]">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Statut</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Platform</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">KC</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Exercice</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Mode</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Caractéristiques</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Itérations</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase whitespace-nowrap w-36">Date</th>
              <th className="text-right px-4 py-3 w-20"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading && (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-400 text-sm">Chargement…</td></tr>
            )}
            {!loading && records.map(r => (
              <tr
                key={r.id}
                className="hover:bg-gray-50 cursor-pointer"
                onClick={() => navigate(`/history/${r.id}`)}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    {STATUS_ICON[r.status]}
                    <span className={`text-xs font-medium ${
                      r.status === 'completed' ? 'text-green-700' :
                      r.status === 'failed' ? 'text-red-700' : 'text-yellow-700'
                    }`}>{STATUS_LABEL[r.status]}</span>
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-indigo-700">{r.platform_id}</td>
                <td className="px-4 py-3 font-mono text-xs text-gray-800">{r.kc_name}</td>
                <td className="px-4 py-3 text-xs text-gray-500 font-mono">{r.exercise_id ?? '—'}</td>
                <td className="px-4 py-3">
                  <span className="px-2 py-0.5 bg-gray-100 text-gray-700 text-xs rounded font-mono">{r.mode}</span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {r.characteristics.map(c => (
                      <span key={c} className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded">{c}</span>
                    ))}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500 text-center">
                  {r.total_iterations ?? '—'}
                </td>
                <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap">{formatDate(r.created_at)}</td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={e => handleDelete(e, r.id)}
                      className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                    <ChevronRight size={14} className="text-gray-400" />
                  </div>
                </td>
              </tr>
            ))}
            {!loading && records.length === 0 && (
              <tr><td colSpan={9} className="px-4 py-8 text-center text-gray-400 text-sm">Aucune génération</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-gray-500">
        <span>{records.length} enregistrement{records.length !== 1 ? 's' : ''}</span>
        <div className="flex gap-2">
          <button
            onClick={() => { const o = Math.max(0, offset - limit); setOffset(o); load(platform, o) }}
            disabled={offset === 0}
            className="px-3 py-1.5 border border-gray-300 rounded-lg disabled:opacity-40 hover:bg-gray-50"
          >
            ← Précédent
          </button>
          <button
            onClick={() => { const o = offset + limit; setOffset(o); load(platform, o) }}
            disabled={records.length < limit}
            className="px-3 py-1.5 border border-gray-300 rounded-lg disabled:opacity-40 hover:bg-gray-50"
          >
            Suivant →
          </button>
        </div>
      </div>
    </div>
  )
}
