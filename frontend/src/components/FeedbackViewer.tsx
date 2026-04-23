import { useState } from 'react'
import { Code2, AlignLeft, Download } from 'lucide-react'

interface ParsedComponent {
  characteristic: string
  type: string
  content?: string
  imageData?: string
  caption?: string
  iterations: number
  qualityScore?: number
}

function parseXML(xml: string): {
  platform?: string
  mode?: string
  level?: string
  language?: string
  generatedAt?: string
  kcName?: string
  kcDesc?: string
  components: ParsedComponent[]
} {
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(xml, 'application/xml')
    const get = (sel: string) => doc.querySelector(sel)?.textContent || ''
    const components: ParsedComponent[] = []
    doc.querySelectorAll('component').forEach((el) => {
      components.push({
        characteristic: el.getAttribute('characteristic') || '',
        type: el.getAttribute('type') || 'text',
        content: el.querySelector('content')?.textContent || undefined,
        imageData: el.querySelector('image_data')?.textContent || undefined,
        caption: el.querySelector('caption')?.textContent || undefined,
        iterations: parseInt(el.querySelector('iterations')?.textContent || '1'),
        qualityScore: el.querySelector('quality_score')
          ? parseFloat(el.querySelector('quality_score')!.textContent || '0')
          : undefined,
      })
    })
    return {
      platform: get('platform'),
      mode: get('mode'),
      level: get('level'),
      language: get('language'),
      generatedAt: get('generated_at'),
      kcName: get('knowledge_component > name'),
      kcDesc: get('knowledge_component > description'),
      components,
    }
  } catch {
    return { components: [] }
  }
}

const CHAR_LABELS: Record<string, string> = {
  logos: 'Logos',
  technical: 'Technical',
  error_pointed: 'Error pointed',
  with_example_unrelated_to_exercise: 'Example (unrelated)',
  with_example_related_to_exercise: 'Example (exercise)',
}

const CHAR_COLORS: Record<string, string> = {
  logos: '#6366F1',
  technical: '#34D399',
  error_pointed: '#F87171',
  with_example_unrelated_to_exercise: '#FBBF24',
  with_example_related_to_exercise: '#F59E0B',
}

export default function FeedbackViewer({ xml }: { xml: string }) {
  const [viewRaw, setViewRaw] = useState(false)
  const parsed = parseXML(xml)

  const handleDownload = () => {
    const blob = new Blob([xml], { type: 'application/xml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `feedback-${Date.now()}.xml`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ borderColor: 'var(--border-hover)' }}
    >
      {/* Header */}
      <div
        className="px-5 py-3.5 border-b flex items-center justify-between"
        style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-2 h-2 rounded-full"
            style={{ background: '#34D399' }}
          />
          <span
            className="font-display font-semibold text-sm"
            style={{ color: 'var(--text-primary)' }}
          >
            Generated feedback
          </span>
          {parsed.platform && (
            <span
              className="text-xs font-mono px-2 py-0.5 rounded"
              style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--accent)' }}
            >
              {parsed.platform}
            </span>
          )}
          {parsed.language && (
            <span
              className="text-xs font-mono px-2 py-0.5 rounded"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
            >
              {parsed.language.toUpperCase()}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setViewRaw(!viewRaw)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors"
            style={{
              background: viewRaw ? 'rgba(99,102,241,0.12)' : 'var(--bg-elevated)',
              color: viewRaw ? 'var(--accent)' : 'var(--text-secondary)',
            }}
          >
            {viewRaw ? <AlignLeft size={12} /> : <Code2 size={12} />}
            {viewRaw ? 'Rendered' : 'Raw XML'}
          </button>
          <button
            onClick={handleDownload}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-colors"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}
          >
            <Download size={12} />
            Download
          </button>
        </div>
      </div>

      {/* Body */}
      {viewRaw ? (
        <pre
          className="p-5 text-xs overflow-auto font-mono"
          style={{
            background: 'var(--bg-elevated)',
            color: 'var(--text-secondary)',
            maxHeight: '480px',
          }}
        >
          {xml}
        </pre>
      ) : (
        <div
          className="p-5"
          style={{ background: 'var(--bg-elevated)' }}
        >
          {/* KC info */}
          {parsed.kcName && (
            <div className="mb-5 pb-4 border-b" style={{ borderColor: 'var(--border)' }}>
              <p
                className="text-xs font-display font-semibold uppercase tracking-widest mb-1"
                style={{ color: 'var(--text-muted)' }}
              >
                Knowledge component
              </p>
              <p
                className="font-display font-semibold"
                style={{ color: 'var(--text-primary)' }}
              >
                {parsed.kcName}
              </p>
              <p className="text-sm mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                {parsed.kcDesc}
              </p>
            </div>
          )}

          {/* Components */}
          <div className="flex flex-col gap-4">
            {parsed.components.map((comp) => (
              <div
                key={comp.characteristic}
                className="rounded-lg border overflow-hidden"
                style={{ borderColor: 'var(--border)' }}
              >
                {/* Component header */}
                <div
                  className="px-4 py-2.5 flex items-center justify-between border-b"
                  style={{
                    background: 'var(--bg-surface)',
                    borderColor: 'var(--border)',
                    borderLeft: `3px solid ${CHAR_COLORS[comp.characteristic] || 'var(--accent)'}`,
                  }}
                >
                  <span
                    className="font-display font-semibold text-sm"
                    style={{ color: CHAR_COLORS[comp.characteristic] || 'var(--accent)' }}
                  >
                    {CHAR_LABELS[comp.characteristic] || comp.characteristic}
                  </span>
                  <div className="flex items-center gap-2">
                    <span
                      className="text-xs font-mono px-2 py-0.5 rounded"
                      style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}
                    >
                      {comp.type}
                    </span>
                    <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {comp.iterations} iter
                    </span>
                    {comp.qualityScore !== undefined && (
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        q={comp.qualityScore.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>

                {/* Component content */}
                <div className="px-4 py-3" style={{ background: 'var(--bg-elevated)' }}>
                  {comp.type === 'image' && comp.imageData ? (
                    <div>
                      <img
                        src={`data:image/png;base64,${comp.imageData}`}
                        alt={comp.caption || 'Annotated screenshot'}
                        className="rounded-lg max-w-full border"
                        style={{ borderColor: 'var(--border)' }}
                      />
                      {comp.caption && (
                        <p
                          className="text-xs mt-2 italic"
                          style={{ color: 'var(--text-secondary)' }}
                        >
                          {comp.caption}
                        </p>
                      )}
                    </div>
                  ) : (
                    <p
                      className="text-sm leading-relaxed whitespace-pre-wrap"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {comp.content}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
