import { useState, useEffect } from 'react'
import { Plus, Pencil, Trash2, Save, X } from 'lucide-react'
import { listKCs, createKC, updateKC, deleteKC } from '../api/client'
import type { KC, KCIn } from '../types'

const EMPTY: KCIn = { platform_id: 'algopython', name: '', description: '', series: null }

export default function KnowledgeComponents() {
  const [kcs, setKCs] = useState<KC[]>([])
  const [editing, setEditing] = useState<KC | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<KCIn>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const load = () => listKCs().then(r => setKCs(r.data))
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm(EMPTY); setCreating(true); setEditing(null) }
  const openEdit = (kc: KC) => {
    setForm({ platform_id: kc.platform_id, name: kc.name, description: kc.description, series: kc.series })
    setEditing(kc); setCreating(false)
  }
  const cancel = () => { setCreating(false); setEditing(null); setError(null) }

  const save = async () => {
    if (!form.name.trim() || !form.description.trim()) { setError('Nom et description requis'); return }
    setSaving(true); setError(null)
    try {
      if (creating) await createKC(form)
      else if (editing) await updateKC(editing.id, form)
      await load(); cancel()
    } catch (e: any) {
      setError(e.response?.data?.detail ?? e.message)
    } finally { setSaving(false) }
  }

  const del = async (kc: KC) => {
    if (!confirm(`Supprimer le KC "${kc.name}" ?`)) return
    await deleteKC(kc.id); load()
  }

  const seriesGroups = kcs.reduce<Record<string, KC[]>>((acc, kc) => {
    const s = kc.series ?? '—'
    if (!acc[s]) acc[s] = []
    acc[s].push(kc)
    return acc
  }, {})

  const filtered = search.trim()
    ? kcs.filter(k =>
        k.name.toLowerCase().includes(search.toLowerCase()) ||
        k.description.toLowerCase().includes(search.toLowerCase())
      )
    : null

  const isEditorOpen = creating || !!editing

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Knowledge Components</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus size={16} />Nouveau KC
        </button>
      </div>

      {/* Editor */}
      {isEditorOpen && (
        <div className="bg-white rounded-xl border border-indigo-200 shadow-sm p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-800">
            {creating ? 'Nouveau KC' : `Modifier ${editing?.name}`}
          </h2>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Nom *</label>
              <input
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                disabled={!!editing}
                placeholder="ex: FO.2.1"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none disabled:bg-gray-50"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Série</label>
              <input
                value={form.series ?? ''}
                onChange={e => setForm(f => ({ ...f, series: e.target.value || null }))}
                placeholder="ex: FO, AL, …"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Description *</label>
            <textarea
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              rows={3}
              placeholder="Description pédagogique complète du KC…"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex gap-3">
            <button
              onClick={save}
              disabled={saving}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-medium px-4 py-2 rounded-lg"
            >
              <Save size={14} />{saving ? 'Sauvegarde…' : 'Sauvegarder'}
            </button>
            <button
              onClick={cancel}
              className="flex items-center gap-2 border border-gray-300 text-gray-700 text-sm px-4 py-2 rounded-lg hover:bg-gray-50"
            >
              <X size={14} />Annuler
            </button>
          </div>
        </div>
      )}

      {/* Search */}
      <input
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Rechercher un KC par nom ou description…"
        className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
      />

      {/* Results */}
      {filtered ? (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Nom</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Série</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Description</th>
                <th className="text-right px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map(kc => (
                <KCRow key={kc.id} kc={kc} onEdit={openEdit} onDelete={del} />
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-400 text-sm">Aucun résultat</td></tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        /* Grouped by series */
        <div className="space-y-4">
          {Object.entries(seriesGroups).sort(([a], [b]) => a.localeCompare(b)).map(([series, items]) => (
            <div key={series} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="px-4 py-2.5 bg-gray-50 border-b border-gray-200 flex items-center gap-2">
                <span className="text-xs font-mono font-semibold text-indigo-700 px-2 py-0.5 bg-indigo-50 rounded">
                  {series}
                </span>
                <span className="text-xs text-gray-500">{items.length} KC{items.length > 1 ? 's' : ''}</span>
              </div>
              <table className="w-full text-sm">
                <tbody className="divide-y divide-gray-100">
                  {items.map(kc => (
                    <KCRow key={kc.id} kc={kc} onEdit={openEdit} onDelete={del} />
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {kcs.length === 0 && (
            <div className="bg-white rounded-xl border border-gray-200 px-4 py-8 text-center text-gray-400 text-sm">
              Aucun KC enregistré
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function KCRow({ kc, onEdit, onDelete }: { kc: KC; onEdit: (kc: KC) => void; onDelete: (kc: KC) => void }) {
  return (
    <tr className="hover:bg-gray-50">
      <td className="px-4 py-3 font-mono text-indigo-700 font-medium whitespace-nowrap">{kc.name}</td>
      <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{kc.series ?? '—'}</td>
      <td className="px-4 py-3 text-gray-600 text-xs">{kc.description}</td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1">
          <button onClick={() => onEdit(kc)} className="p-1.5 text-gray-400 hover:text-indigo-600 rounded"><Pencil size={14} /></button>
          <button onClick={() => onDelete(kc)} className="p-1.5 text-gray-400 hover:text-red-600 rounded"><Trash2 size={14} /></button>
        </div>
      </td>
    </tr>
  )
}
