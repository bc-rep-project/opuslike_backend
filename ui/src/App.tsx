import React, { useEffect, useMemo, useState } from 'react'
// NOTE: Several functions used in the component were not listed in the original import.
// I've added them here for completeness based on their usage in the code.
import {
  createVideo, listVideos, getMoments, renderClips, getVideo, listClipsForVideo, subscribeChannel, syncAllChannels, publishClipToYouTube, makeThumbnail, type Video, type Moment,
  getLeaderboard, listFailedJobs, retryJob, deleteJob, getHealth, listAlertChannels, getAlertSettings, setAlertSettings, addAlertChannel, sendAlertTest, suggestTitles,
  createAutopost, publishClipToTikTok, makeABThumbs, startABTest, setStyleVariant, makeStylePack
} from './api'

// FIX: Use a global declaration to correctly augment the ImportMeta type for Vite's environment variables.
declare global {
    interface ImportMeta {
        readonly env: {
            readonly VITE_API_URL: string;
            readonly VITE_API_KEY: string;
        };
    }
}

function formatTime(s: number) {
  const hh = Math.floor(s / 3600)
  const mm = Math.floor((s % 3600) / 60)
  const ss = Math.floor(s % 60)
  return (hh ? String(hh).padStart(2,'0')+':' : '') + String(mm).padStart(2,'0') + ':' + String(ss).padStart(2,'0')
}

export default function App() {
  const [videos, setVideos] = useState<Video[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [url, setUrl] = useState('')
  const [moments, setMoments] = useState<Moment[]>([])
  const [loadingMoments, setLoadingMoments] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [embedId, setEmbedId] = useState<string | null>(null)
  const [ytUrl, setYtUrl] = useState<string | null>(null)
  const [selectedSegs, setSelectedSegs] = useState<Record<string, boolean>>({})
  const [clips, setClips] = useState<{clip_id:string,status:string,storage_url?:string, thumbnail_url?: string, metrics?: any, style_variants?: any[]}[]>([])
  const [channelId, setChannelId] = useState('')
  const [keywords, setKeywords] = useState('')

  async function getFreshLink(id: string) {
    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
      const API_KEY = import.meta.env.VITE_API_KEY || 'dev-key'
      const res = await fetch(`${API_URL}/clips/${id}/signed_url`, { headers: { 'x-api-key': API_KEY } })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const url = data.url
      if (url) window.open(url, '_blank')
    } catch(e) { alert(String(e)) }
  }

  async function refresh() {
    const res = await listVideos()
    setVideos(res.videos)
    if (!selected && res.videos.length) {
      setSelected(res.videos[0].id)
    }
  }

  useEffect(() => { refresh().catch(console.error) }, [])

  useEffect(() => {
    if (!selected) return
    setLoadingMoments(true)
    Promise.all([getMoments(selected, 12), getVideo(selected)])
      .then(([m, v]) => {
        setMoments(m.moments || [])
        setYtUrl(v.youtube_url)
        try {
          const url = new URL(v.youtube_url)
          const id = url.searchParams.get('v')
          setEmbedId(id)
        } catch { setEmbedId(null) }
      })
      .catch(console.error)
      .finally(() => setLoadingMoments(false))
  }, [selected])

  // Poll clip list
  useEffect(() => {
    if (!selected) return
    let cancelled = false
    async function load() {
      try {
        const res = await listClipsForVideo(selected!)
        if (!cancelled) setClips(res.clips || [])
      } catch {}
    }
    load()
    const id = setInterval(load, 3000)
    return () => { cancelled = true; clearInterval(id) }
  }, [selected])

  async function onCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!url) return
    setCreating(true)
    try {
      const res = await createVideo(url)
      await refresh()
      setSelected(res.video_id)
      setUrl('')
    } catch (e) {
      alert(String(e))
    } finally {
      setCreating(false)
    }
  }

  const selectedIds = useMemo(() => Object.entries(selectedSegs).filter(([,v]) => v).map(([k]) => k), [selectedSegs])

  async function onRender() {
    if (!selected || selectedIds.length === 0) return
    setRendering(true)
    try {
      const res = await renderClips(selected, selectedIds, '9:16')
      alert(`Queued ${res.clip_ids.length} render job(s). You'll see links below when ready.`)
      setSelectedSegs({})
    } catch (e) {
      alert(String(e))
    } finally {
      setRendering(false)
    }
  }

  const handleRefreshMoments = () => {
    if (!selected) return;
    setLoadingMoments(true);
    getMoments(selected, 12)
        .then(m => setMoments(m.moments || []))
        .finally(() => setLoadingMoments(false));
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="h1">Opus-like</div>
        <div className="small">Queue a YouTube URL → rank moments → render clips.</div>
        <div className="hr"></div>

        <form onSubmit={onCreate} className="card" style={{ display: 'grid', gap: 8 }}>
          <label className="label">YouTube URL</label>
          <input className="input" placeholder="https://www.youtube.com/watch?v=..." value={url} onChange={e => setUrl(e.target.value)} />
          <button className="button" disabled={creating}>{creating ? 'Queuing...' : 'Queue Ingest'}</button>
        </form>

        <div className="hr"></div>
        <div className="card" style={{ display: 'grid', gap: 8 }}>
          <div className="h1">Channels</div>
          <input className="input" placeholder="YouTube Channel ID (UC...)" value={channelId} onChange={e => setChannelId(e.target.value)} />
          <input className="input" placeholder="Keywords (comma-separated)" value={keywords} onChange={e => setKeywords(e.target.value)} />
          <div className="flex">
            <button className="badge" onClick={async () => { if (!channelId) return; await subscribeChannel(channelId, 3, "08:00", keywords.split(',').map(s=>s.trim()).filter(Boolean)); alert('Subscribed!'); }}>Subscribe</button>
            <button className="badge" onClick={async () => { const r = await syncAllChannels(); alert('Queued sync for ' + r.queued + ' channel(s)') }}>Sync now</button>
          </div>
          <div className="small">Scheduler fetches new uploads and queues ingest; at the set time it auto-renders top clips.</div>
        </div>

        <div className="hr"></div>
        <div className="label" style={{ marginBottom: 8 }}>Recent videos</div>
        <div className="list">
          {videos.map(v => (
            <div className="item" key={v.id}>
              <div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{v.id.slice(0,8)}</div>
                <div className="small">{v.status}</div>
              </div>
              <button className="badge" onClick={() => setSelected(v.id)}>Open</button>
            </div>
          ))}
          {videos.length === 0 && <div className="small">No videos yet.</div>}
        </div>
        <div className="hr"></div>
        <div className="label" style={{ marginBottom: 8 }}>Leaderboard (24h)</div>
        <Leaderboard />
        <div className="hr"></div>
        <div className="label" style={{ marginBottom: 8 }}>Admin: Failed jobs</div>
        <AdminJobs />
        <div className="hr"></div>
        <div className="label" style={{ marginBottom: 8 }}>Health</div>
        <HealthPanel />
        <div className="hr"></div>
        <div className="label" style={{ marginBottom: 8 }}>Alerts</div>
        <AlertsPanel />
      </aside>

      <main className="main">
        {!selected ? (
          <div className="small">Select a video</div>
        ) : (
          <>
            <div className="flex" style={{ alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div className="h1">Video {selected.slice(0,8)}</div>
                <div className="small">{ytUrl}</div>
              </div>
              <div className="flex">
                <button className="badge" onClick={handleRefreshMoments}>Refresh moments</button>
                <button className="badge" onClick={() => refresh()}>Refresh list</button>
                <button className="badge" onClick={async () => { try { const r = await suggestTitles(selected!); alert('Title ideas:\n\n' + (r.suggestions || []).join('\n')); } catch(e) { alert(String(e)) } }}>Suggest titles</button>
              </div>
            </div>

            <div className="hr"></div>

            {embedId && (
              <iframe
                width="720" height="405"
                src={`https://www.youtube.com/embed/${embedId}?start=0&autoplay=0`}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
                title="YouTube preview"
              />
            )}

            <div className="hr"></div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div className="h1">Top moments</div>
              <div className="small">{loadingMoments ? 'Loading…' : `${moments.length} candidates`}</div>
            </div>

            <div className="segments">
              {moments.map(m => (
                <div className="segment" key={m.segment_id}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ fontWeight: 700 }}>{formatTime(m.start)}–{formatTime(m.end)}</div>
                    <div className="small">score: {m.score.toFixed(3)}</div>
                  </div>
                  <div className="small">reason: {Object.entries(m.reason || {}).map(([k,v]) => `${k}:${(v as number).toFixed ? (v as number).toFixed(2) : v}`).join('  ')}</div>
                  {ytUrl && (
                    <div className="controls">
                      <a target="_blank" rel="noreferrer" className="badge" href={`${ytUrl}${ytUrl.includes('?') ? '&' : '?'}t=${Math.floor(m.start)}s`}>Open on YouTube →</a>
                      <label className="badge" style={{ cursor: 'pointer' }}>
                        <input type="checkbox" style={{ marginRight: 6 }} checked={!!selectedSegs[m.segment_id]} onChange={e => setSelectedSegs(s => ({ ...s, [m.segment_id]: e.target.checked }))} />
                        select
                      </label>
                    </div>
                  )}
                </div>
              ))}
              {moments.length === 0 && <div className="small">No moments yet. If the worker just ran TRANSCRIBE, wait for ANALYZE to finish and click “Refresh moments”.</div>}
            </div>

            <div className="hr"></div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div className="small">{selectedIds.length} selected</div>
              <div className="flex">
                <button className="button" disabled={rendering || selectedIds.length === 0} onClick={onRender}>
                  {rendering ? 'Queuing…' : 'Render selected'}
                </button>
              </div>
            </div>

            <div className="hr"></div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div className="h1">Rendered clips</div>
              <div className="small">{clips.length} total</div>
            </div>

            <div className="segments">
              {clips.map(c => {
                const views = c.metrics?.youtube_timeseries?.slice(-1)[0]?.views;
                return (
                  <div className="segment" key={c.clip_id}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ fontWeight: 700 }}>{c.clip_id.slice(0,8)}</div>
                      <div className="small">status: {c.status}{views !== undefined ? ` • views: ${views}` : ''}</div>
                    </div>
                    {c.thumbnail_url && (
                      <div className="controls">
                        <img src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${c.thumbnail_url}`} alt="thumbnail" style={{ height: 96, borderRadius: 8, border: '1px solid #202536' }} />
                        <a className="badge" target="_blank" rel="noreferrer" href={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${c.thumbnail_url}`} download>Download thumbnail</a>
                      </div>
                    )}
                    {Array.isArray(c.style_variants) && c.style_variants.length > 0 && (
                      <div className="controls" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
                        {c.style_variants.map((sv:any) => (
                          <div key={sv.key} className="card" style={{ padding: 6, textAlign: 'center' }}>
                            <img src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${sv.url}`} alt={sv.key} style={{ width: '100%', height: 96, objectFit: 'cover', borderRadius: 8, border: '1px solid #202536' }} />
                            <div className="small" style={{ marginTop: 4 }}>{sv.key}</div>
                            <button className="badge" onClick={async () => { try { await setStyleVariant(c.clip_id, sv.key, true); alert('Set on YouTube'); } catch(e) { alert(String(e)) } }}>Use</button>
                          </div>
                        ))}
                      </div>
                    )}
                    {c.storage_url ? (
                      <div className="controls">
                        <a className="badge" target="_blank" rel="noreferrer" href={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${c.storage_url}`}>Open clip →</a>
                        <a className="badge" target="_blank" rel="noreferrer" href={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${c.storage_url}`} download>Download</a>
                        <button className="badge" onClick={async () => { const A = prompt('Title A?', 'Option A'); if (!A) return; const B = prompt('Title B?', 'Option B'); if (!B) return; try { await makeABThumbs(c.clip_id, A, B); alert('A/B thumbnails generated'); } catch(e) { alert(String(e)) } }}>Make A/B thumbnails</button>
                        <button className="badge" onClick={async () => { try { await startABTest(c.clip_id, true); alert('A/B test started'); } catch(e) { alert(String(e)) } }}>Start A/B test</button>
                        <button className="badge" onClick={async () => { try { await startABTest(c.clip_id, false); alert('A/B test stopped'); } catch(e) { alert(String(e)) } }}>Stop A/B test</button>
                        <button className="badge" onClick={async () => { const title = prompt('YouTube title?', 'My Clip'); if (!title) return; const desc = ''; try { await publishClipToYouTube(c.clip_id, title, desc, keywords.split(',').map(s=>s.trim()).filter(Boolean), 'unlisted'); alert('Upload queued'); } catch(e) { alert(String(e)) } }}>Publish to YouTube</button>
                        <button className="badge" onClick={async () => { const title = prompt('TikTok caption?', ''); if (title===null) return; try { await publishClipToTikTok(c.clip_id, title || ''); alert('TikTok upload queued'); } catch(e) { alert(String(e)) } }}>Publish to TikTok</button>
                        <button className="badge" onClick={() => getFreshLink(c.clip_id)}>Get fresh link</button>
                        <button className="badge" onClick={async () => { const title = prompt('Thumbnail title?', ''); try { await makeThumbnail(c.clip_id, title || ''); alert('Thumbnail generated'); } catch(e) { alert(String(e)) } }}>Make thumbnail</button>
                        <button className="badge" onClick={async () => { const title = prompt('Title for styles?', ''); if (!title) return; try { await makeStylePack(c.clip_id, title || ''); alert('Style pack generated'); } catch(e) { alert(String(e)) } }}>Make style pack</button>
                      </div>
                    ) : (
                      <div className="small">waiting for file…</div>
                    )}
                  </div>
                )
              })}
              {clips.length === 0 && <div className="small">No clips yet.</div>}
            </div>

            <div className="hr"></div>
            <div className="card" style={{ display: 'grid', gap: 8 }}>
              <div className="h1">Autopost (daily winner / digest)</div>
              <label className="label">Destination</label>
              <select className="input" id="apKind"><option value="webhook">Webhook</option><option value="email">Email</option></select>
              <label className="label">Webhook URL or emails (comma-separated)</label>
              <input className="input" id="hookUrl" placeholder="https://example.com/webhook OR a@b.com,b@c.com" />
              <label className="label">Daily time (UTC)</label>
              <input className="input" id="hookTime" defaultValue="09:00" />
              <label className="label">Template</label>
              <input className="input" id="hookTpl" defaultValue="{title} — {views_24h} views in 24h\n{url}" />
              <div className="flex">
                <button className="badge" onClick={async () => {
                  const url = (document.getElementById('hookUrl') as HTMLInputElement).value
                  const time = (document.getElementById('hookTime') as HTMLInputElement).value
                  const tpl = (document.getElementById('hookTpl') as HTMLInputElement).value
                  const kind = (document.getElementById('apKind') as HTMLSelectElement).value as any
                  if (!url) return alert(kind==='email' ? 'Enter at least one email' : 'Enter a webhook URL')
                  await createAutopost(kind, url, tpl, time, true)
                  alert('Autopost created')
                }}>Save</button>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  )
}


function Leaderboard() {
  const [items, setItems] = useState<any[]>([])
  useEffect(() => { getLeaderboard(10).then(r => setItems(r.items || [])) }, [])
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  return (
    <div className="grid" style={{ gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
      {items.map(it => (
        <div key={it.clip_id} className="card" style={{ padding: 8 }}>
          {it.thumbnail_url && <img src={`${apiUrl}${it.thumbnail_url}`} alt="" style={{ width: '100%', height: 120, objectFit: 'cover', borderRadius: 8, border: '1px solid #202536' }} />}
          <div className="small" style={{ marginTop: 6 }}>{it.title}</div>
          <div className="small">+{it.views_24h} views / 24h{typeof it.ctr_proxy === 'number' ? ` • CTR ~ ${ (it.ctr_proxy).toFixed(1) }%` : ''}</div>
          <div className="flex">
            {it.youtube_url && <a className="badge" target="_blank" rel="noreferrer" href={it.youtube_url}>YouTube</a>}
            {it.storage_url && <a className="badge" target="_blank" rel="noreferrer" href={`${apiUrl}${it.storage_url}`}>Open</a>}
          </div>
        </div>
      ))}
    </div>
  )
}


function AdminJobs() {
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const reload = async () => {
    setLoading(true)
    try { const r = await listFailedJobs(100); setJobs(r.jobs || []) } finally { setLoading(false) }
  }
  useEffect(() => { reload() }, [])
  return (
    <div>
      <div className="flex" style={{ marginBottom: 8 }}>
        <button className="badge" onClick={reload} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
      </div>
      <div className="grid" style={{ gridTemplateColumns: '1fr 5fr 2fr 2fr 2fr', gap: 8 }}>
        <div className="small bold">Type</div>
        <div className="small bold">Error</div>
        <div className="small bold">Updated</div>
        <div className="small bold">Attempts</div>
        <div className="small bold">Actions</div>
        {jobs.map((j:any) => (
          <React.Fragment key={j.id}>
            <div className="small">{j.type}</div>
            <div className="small" title={JSON.stringify(j.payload)} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{j.error || '-'}</div>
            <div className="small">{j.updated_at?.replace('T',' ').slice(0,19)}</div>
            <div className="small">{j.attempts || 0}</div>
            <div className="small">
              <button className="badge" onClick={async () => { await retryJob(j.id); alert('Requeued'); reload() }}>Retry</button>
              <button className="badge" onClick={async () => { await deleteJob(j.id); reload() }} style={{ marginLeft: 6 }}>Delete</button>
            </div>
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}


function Dot({ ok }: { ok: boolean }) {
  return <span style={{ display:'inline-block', width:10, height:10, borderRadius:6, background: ok ? '#22c55e' : '#ef4444', marginRight:8 }} />
}
function Row({ label, ok, extra }: any) {
  return <div className="flex" style={{ alignItems:'center', gap:8 }}><Dot ok={ok}/><div className="small" style={{ width: 140 }}>{label}</div><div className="small">{extra}</div></div>
}
function HealthPanel() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const load = async () => { setLoading(true); try { const r = await getHealth(); setData(r) } finally { setLoading(false) } }
  useEffect(() => { load() }, [])
  const c = data?.checks || {}
  return (
    <div className="card">
      <div className="flex" style={{ justifyContent:'space-between', marginBottom:8 }}>
        <div className="small">Status: <b>{data?.status || '-'}</b> • Uptime: {data ? Math.floor(data.uptime_sec/60) : 0} min</div>
        <button className="badge" onClick={load} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
      </div>
      <Row label="Database" ok={!!c.db?.ok} extra={c.db?.error ? ('err: ' + c.db.error) : ''} />
      <Row label="Redis" ok={!!c.redis?.ok} extra={typeof c.redis?.queue_len === 'number' ? ('queue=' + c.redis.queue_len) : (c.redis?.error || '')} />
      <Row label="Storage" ok={!!c.storage?.ok} extra={c.storage?.media_root} />
      <div className="small" style={{ marginTop:8 }}>Prometheus: <code>{(import.meta.env.VITE_API_URL || 'http://localhost:8000') + '/metrics'}</code></div>
    </div>
  )
}


function AlertsPanel() {
  const [channels, setChannels] = useState<any[]>([])
  const [s, setS] = useState<any>({ queue_threshold: 100, debounce_min: 10, health_enabled: true })
  const reload = async () => {
    const ch = await listAlertChannels(); setChannels(ch.channels || [])
    const st = await getAlertSettings(); setS(st)
  }
  useEffect(() => { reload() }, [])
  const save = async () => {
    await setAlertSettings(Number(s.queue_threshold||100), Number(s.debounce_min||10), !!s.health_enabled); alert('Saved')
  }
  const add = async () => {
    const kind = (document.getElementById('alertKind') as HTMLSelectElement).value as any
    const url = (document.getElementById('alertUrl') as HTMLInputElement).value
    if (!url) return alert('Enter URL')
    await addAlertChannel(kind, url, true); (document.getElementById('alertUrl') as HTMLInputElement).value=''; await reload()
  }
  return (
    <div className="card" style={{ display:'grid', gap:8 }}>
      <div className="flex" style={{ gap:8 }}>
        <select id="alertKind" className="input" defaultValue="slack">
          <option value="slack">Slack webhook</option>
          <option value="webhook">Generic webhook</option>
        </select>
        <input id="alertUrl" className="input" placeholder="https://hooks.slack.com/..." style={{ flex:1 }} />
        <button className="badge" onClick={add}>Add channel</button>
      </div>
      <div className="small">Channels: {channels.length ? channels.map((c:any) => c.kind).join(', ') : 'none'}</div>
      <div className="hr"></div>
      <div className="flex" style={{ gap:8 }}>
        <label className="label">Queue threshold</label>
        <input className="input" value={s.queue_threshold} onChange={e => setS({...s, queue_threshold: e.target.value})} style={{ width:120 }} />
        <label className="label">Debounce (min)</label>
        <input className="input" value={s.debounce_min} onChange={e => setS({...s, debounce_min: e.target.value})} style={{ width:120 }} />
        <label className="label"><input type="checkbox" checked={!!s.health_enabled} onChange={e => setS({...s, health_enabled: e.target.checked})} style={{ marginRight:8 }} /> Health change alerts</label>
        <button className="badge" onClick={save}>Save</button>
        <button className="badge" onClick={() => sendAlertTest().then(()=>alert('Test queued'))}>Send test</button>
      </div>
    </div>
  )
}