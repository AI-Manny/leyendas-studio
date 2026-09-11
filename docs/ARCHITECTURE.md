# Architecture Map — Leyendas Studio

Last updated: 2026-09-11

## Overview

Leyendas Studio is a single-page app + a set of stateless Vercel Python
serverless functions that turn a legend premise into a finished, captioned,
vertical (9:16) short-form video, and (optionally) publish it to
YouTube/TikTok/Instagram.

There is no database and no server process — every `api/*.py` function is a
standalone Vercel Python Function (`BaseHTTPRequestHandler`) that proxies to
one external SaaS API per step. State lives only in the browser tab
(`index.html`'s in-memory JS) while a user works through the pipeline.

## Components

| File | Role |
|---|---|
| `index.html` | The entire frontend: UI + orchestration JS. Drives the pipeline by calling the `api/*` endpoints in sequence and holding pipeline state (title/premise/scenes/urls) in memory. |
| `middleware.js` | Vercel Edge Middleware. Site-wide HTTP Basic Auth gate using `SITE_USER`/`SITE_PASS` env vars; if either is unset, auth is disabled (fail-open by design so the site can't be locked out). |
| `api/generate.py` | `POST` — turns `{title, premise, region}` into a JSON episode package (title, hook, script, scenes with image prompts, per-platform captions) via an LLM. |
| `api/image.py` | `POST` — turns one `{prompt}` into one generated 9:16 image URL via fal.ai. |
| `api/compile.py` | `POST` submits a render job (scene images + narration + voice) to JSON2Video; `GET ?id=` polls render status and returns the final MP4 URL. |
| `api/publish.py` | `POST` — publishes a finished video + per-platform captions to YouTube/TikTok/Instagram via Ayrshare. Called from `index.html` once a compile finishes, via a platform checklist + "Publish" button. |
| `vercel.json` | Rewrites `/` → `/index.html`. |
| `requirements.txt` | Intentionally empty — every function uses only the Python standard library (`urllib`, `json`, `http.server`), so there is no dependency install step. |

## Pipeline (request flow)

```
Browser (index.html)
  │
  │ 1. POST /api/generate  {title, premise, region}
  ▼
api/generate.py  ──▶  Groq → OpenAI → Anthropic (first key found)  ──▶  demo fallback if no key
  │  returns {title, hook, script, scenes[], captions{youtube,tiktok,instagram}}
  ▼
Browser: for each scene
  │ 2. POST /api/image  {prompt: scene.image_prompt}
  ▼
api/image.py  ──▶  fal.ai flux/schnell  ──▶  {url}
  │  (repeated once per scene, sequentially in the browser loop)
  ▼
Browser: has narration + all scene image URLs
  │ 3. POST /api/compile  {title, narration, scenes:[{image_url}], voice}
  ▼
api/compile.py  ──▶  JSON2Video "movies" API  ──▶  {projectId}
  │ 4. GET /api/compile?id=<projectId>   (polled by the browser until done)
  ▼
api/compile.py  ──▶  JSON2Video status  ──▶  {status, url: <mp4 or null>}
  │  browser now has the finished MP4 URL
  ▼
(not wired up yet) api/publish.py  ──▶  Ayrshare /api/post  ──▶  YouTube/TikTok/Instagram
```

Every hop is stateless: each `api/*.py` call carries all the data it needs in
the request body/query string; nothing is persisted server-side between
steps. The browser tab is the only place the in-progress pipeline state
lives.

## External services & required env vars

| Service | Used by | Env var | Notes |
|---|---|---|---|
| Groq | `api/generate.py` | `GROQ_API_KEY` | Tried first; `llama-3.3-70b-versatile`. |
| OpenAI | `api/generate.py` | `OPENAI_API_KEY` | Fallback if no Groq key; `gpt-5.6-luna`. |
| Anthropic | `api/generate.py` | `ANTHROPIC_API_KEY` | Fallback if neither above; `claude-opus-5` with structured JSON output and the server-side refusal fallback. |
| (provider pick) | `api/generate.py` | `LLM_PROVIDER` | Optional: `groq`, `openai` or `anthropic` forces one provider when several keys are set. |
| fal.ai | `api/image.py` | `FAL_KEY` | `flux/schnell` model, portrait images. |
| JSON2Video | `api/compile.py` | `JSON2VIDEO_KEY` | Renders scenes + TTS narration + subtitles into an MP4. |
| Ayrshare | `api/publish.py` | `AYRSHARE_KEY` | Cross-posts to YouTube/TikTok/Instagram; accounts must be linked in the Ayrshare dashboard first. |
| (site gate) | `middleware.js` | `SITE_USER`, `SITE_PASS` | HTTP Basic Auth for the whole site; gate is disabled if either is unset. |

If `api/generate.py` finds no LLM key (or the request body has `"demo": true`),
it returns a canned `demo_package()` instead of calling out — this is what
lets the whole pipeline be exercised end-to-end with zero keys configured.

## Notable gaps / inconsistencies

- `api/publish.py` is fully implemented but `index.html` never calls
  `/api/publish` — publishing is currently a manual/out-of-band step.
- No automated tests and no CI config in the repo.
- No persistence layer: if the browser tab is closed mid-pipeline, all
  progress (generated script, images, compile project id) is lost.
