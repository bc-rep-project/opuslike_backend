const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const API_KEY = import.meta.env.VITE_API_KEY || 'dev-key'

async function api(path: string, init?: RequestInit) {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'x-api-key': API_KEY,
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    const txt = await res.text()
    throw new Error(`HTTP ${res.status}: ${txt}`)
  }
  return res.json()
}

export type Video = { id: string; youtube_url: string; status: string; created_at?: string }
export type Moment = { segment_id: string; start: number; end: number; score: number; reason?: Record<string, number> }
export type Clip = { clip_id: string; status: string; storage_url?: string; output_path?: string }

export const listVideos = () => api('/videos')
export const createVideo = (youtube_url: string) => api('/videos', { method: 'POST', body: JSON.stringify({ youtube_url }) })
export const getVideo = (id: string) => api(`/videos/${id}`)
export const getMoments = (id: string, limit=12) => api(`/videos/${id}/moments?limit=${limit}`)
export const renderClips = (video_id: string, segment_ids: string[], aspect_ratio='9:16') =>
  api(`/clips/${video_id}/render`, { method: 'POST', body: JSON.stringify({ segment_ids, aspect_ratio }) })
export const getClip = (clip_id: string) => api(`/clips/${clip_id}`)
export const listClipsForVideo = (video_id: string) => api(`/clips/video/${video_id}`)


export const subscribeChannel = (channel_id: string, auto_render_top_k=3, daily_post_time="08:00", keywords: string[] = []) =>
  api('/channels/subscribe', { method: 'POST', body: JSON.stringify({ channel_id, auto_render_top_k, daily_post_time, keywords }) })

export const syncAllChannels = () => api('/channels/sync_all', { method: 'POST' })


export const publishClipToYouTube = (clip_id: string, title: string, description: string, tags: string[] = [], privacyStatus: string = 'unlisted') =>
  api(`/clips/${clip_id}/publish/youtube`, { method: 'POST', body: JSON.stringify({ title, description, tags, privacyStatus }) })


export const makeThumbnail = (clip_id: string, title: string, aspect_ratio='9:16') =>
  api(`/clips/${clip_id}/thumbnail`, { method: 'POST', body: JSON.stringify({ title, aspect_ratio }) })


export const suggestTitles = (video_id: string, use_llm=false) =>
  api(`/videos/${video_id}/titles`, { method: 'POST', body: JSON.stringify(use_llm) })

export const makeABThumbs = (clip_id: string, title_a: string, title_b: string, aspect_ratio='9:16') =>
  api(`/clips/${clip_id}/thumbnails/ab`, { method: 'POST', body: JSON.stringify({ title_a, title_b, aspect_ratio }) })

export const startABTest = (clip_id: string, start=true) =>
  api(`/clips/${clip_id}/thumbnails/ab/start`, { method: 'POST', body: JSON.stringify({ start }) })


export const makeStylePack = (clip_id: string, title: string, aspect_ratio='9:16') =>
  api(`/clips/${clip_id}/thumbnails/styles`, { method: 'POST', body: JSON.stringify({ title, aspect_ratio }) })

export const setStyleVariant = (clip_id: string, key: string, set_on_youtube=true) =>
  api(`/clips/${clip_id}/thumbnails/set`, { method: 'POST', body: JSON.stringify({ key, set_on_youtube }) })


export const getLeaderboard = (limit=10) => api(`/analytics/leaderboard?limit=${limit}`)

export const createAutopost = (platform: 'webhook'|'x', endpoint: string|null, template: string, daily_time: string, enabled=true) =>
  api('/autoposts', { method: 'POST', body: JSON.stringify({ platform, endpoint, template, daily_time, enabled }) })

export const listAutoposts = () => api('/autoposts')

export const runAutopostNow = (id: string) => api(`/autoposts/${id}/run_now`, { method: 'POST' })


export const publishClipToTikTok = (clip_id: string, title: string) =>
  api(`/clips/${clip_id}/publish/tiktok`, { method: 'POST', body: JSON.stringify({ title }) })


export const listFailedJobs = (limit=100) => api(`/admin/jobs?status=error&limit=${limit}`)
export const retryJob = (id: string) => api(`/admin/jobs/${id}/retry`, { method: 'POST', body: JSON.stringify({}) })
export const deleteJob = (id: string) => api(`/admin/jobs/${id}`, { method: 'DELETE' })


export const getHealth = () => api('/health')


export const addAlertChannel = (kind: 'slack'|'webhook', endpoint: string, enabled=true) =>
  api('/alerts/channels', { method: 'POST', body: JSON.stringify({ kind, endpoint, enabled }) })

export const listAlertChannels = () => api('/alerts/channels')

export const getAlertSettings = () => api('/alerts/settings')

export const setAlertSettings = (queue_threshold: number, debounce_min: number, health_enabled: boolean) =>
  api('/alerts/settings', { method: 'POST', body: JSON.stringify({ queue_threshold, debounce_min, health_enabled }) })

export const sendAlertTest = () => api('/alerts/test', { method: 'POST' })
