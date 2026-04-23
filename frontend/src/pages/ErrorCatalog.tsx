import { useState, useEffect } from 'react'
import { Plus, Pencil, Trash2, Save, X } from 'lucide-react'
import { listErrors, listKCs, createError, updateError, deleteError } from '../api/client'
import type { ErrorEntry, ErrorEntryIn, KC } from '../types'

const EMPTY: ErrorEntryIn = { platform_id: 'algopython', tag: '', description: '', related_kc_names: [] }

export default function ErrorCatalog() {
  const [errors, setErrors] = useState<ErrorEntry[]>([])
  const [kcs, setKCs] = useState<KC[]>([])
  const [editing, setEditing] = useState<ErrorEntry | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState<ErrorEntryIn>(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const load = () => {
    listErrors().then(r => setErrors(r.data))
    listKCs().then(r => setKCs(r.data))
  }
  useEffect(() => { load() }, [])

  const openCreate = () => { setForm(EMPTY); setCreating(true); setEditing(null) }
  const openEdit = (e: ErrorEntry) => {
    setForm({ platform_id: e.platform_id, tag: e.tag, description: e.description, related_kc_names: [...e.related_kc_names] })
    setEditing(e); setCreating(false)
  }
  const cancel = () => { setCreating(false); setEditing(null); setError(null) }

  const save = async () => {
    if (!form.tag.trim() || !form.description.trim()) { setError('Tag et description requis'); return }
    setSaving(true); setError(null)
    try {
      if (creating) await createError(form)
      else if (editing) await updateError(editing.id, form)
      await load(); cancel()
    } catch (e: any) {
      setError(e.response?.data?.detail ?? e.message)
    } finally { setSaving(false) }
  }

  const del = async (entry: ErrorEntry) => {
    if (!confirm(`Supprimer l'erreur "${entry.tag}" ?`)) return
    await deleteError(entry.id); load()
  }

  const toggleKC = (name: string) =>
    setForm(f => ({
      ...f,
      related_kc_names: f.related_kc_names.includes(name)
        ? f.related_kc_names.filter(k => k !== name)
        : [...f.related_kc_names, name],
    }))

  const displayed = search.trim()
    ? errors.filter(e =>
        e.tag.toLowerCase().includes(search.toLowerCase()) ||
        e.description.toLowerCase().includes(search.toLowerCase())
      )
    : errors

  const isEditorOpen = creating || !!editing

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-gray-900">Catalogue d'erreurs</h1>
        <button
          onClick={openCreate}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus size={16} />Nouvelle erreur
        </button>
      </div>

      {/* Editor */}
      {isEditorOpen && (
        <div className="bg-white rounded-xl border border-indigo-200 shadow-sm p-6 space-y-4">
          <h2 className="text-base font-semibold text-gray-800">
            {creating ? 'Nouvelle erreur' : `Modifier ${editing?.tag}`}
          </h2>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Tag *</label>
            <input
              value={form.tag}
              onChange={e => setForm(f => ({ ...f, tag: e.target.value }))}
              disabled={!!editing}
              placeholder="ex: WRONG_CONDITION, MISSING_RETURN, …"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-indigo-500 focus:outline-none disabled:bg-gray-50"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Description *</label>
            <textarea
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              rows={3}
              placeholder="Description de l'erreur typique et de son impact pédagogique…"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none resize-none"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-600 mb-2">KCs associés</label>
            <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto p-2 border border-gray-200 rounded-lg">
              {kcs.map(k => (
                <button
                  key={k.id}
                  type="button"
                  onClick={() => toggleKC(k.name)}
                  className={`px-2 py-1 rounded text-xs border transition-colors ${
                    form.related_kc_names.includes(k.name)
                      ? 'bg-indigo-100 border-indigo-400 text-indigo-800 font-medium'
                      : 'bg-white border-gray-300 text-gray-600 hover:border-indigo-300'
                  }`}
                >
                  {k.name}
                </button>
              ))}
              {kcs.length === 0 && <span className="text-xs text-gray-400">Aucun KC disponible</span>}
            </div>
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
        placeholder="Rechercher par tag ou description…"
        className="w-full border border-gray-300 rounded-lg px-4 py-2 text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
      />

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Tag</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">Description</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase">KCs liés</th>
              <th className="text-right px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {displayed.map(entry => (
              <tr key={entry.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-mono text-red-700 font-medium whitespace-nowrap">{entry.tag}</td>
                <td className="px-4 py-3 text-gray-600 text-xs max-w-xs">{entry.description}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap gap-1">
                    {entry.related_kc_names.map(name => (
                      <span key={name} className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded font-mono">
                        {name}
                      </span>
                    ))}
                    {entry.related_kc_names.length === 0 && <span className="text-gray-400 text-xs">—</span>}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1">
                    <button onClick={() => openEdit(entry)} className="p-1.5 text-gray-400 hover:text-indigo-600 rounded"><Pencil size={14} /></button>
                    <button onClick={() => del(entry)} className="p-1.5 text-gray-400 hover:text-red-600 rounded"><Trash2 size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {displayed.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-gray-400 text-sm">Aucune erreur enregistrée</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
