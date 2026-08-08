"""
Vercel serverless function: publish a finished video to YouTube, TikTok, Instagram
via Ayrshare's posting API.

POST /api/publish
  Body: {"videoUrl": "https://...mp4", "title": "...",
         "captions": {"youtube": "...", "tiktok": "...", "instagram": "..."},
         "platforms": ["youtube","tiktok","instagram"]}   # platforms optional
  -> returns Ayrshare's full response (per-platform success / error) so you can
     see exactly what each network did.

Add your key in Vercel: Settings -> Environment Variables -> AYRSHARE_KEY
(sign up at ayrshare.com; you must link your YouTube/TikTok/Instagram accounts
in the Ayrshare dashboard first. Instagram must be a Business/Creator account.
TikTok may post as a private draft until your Ayrshare app passes TikTok's audit.)
Standard library only.
"""
import json, os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
API = "https://api.ayrshare.com/api/post"


def _key(name):
    v = os.getenv(name)
    return v.strip() if v else v


def _post(url, key, payload):
    headers = {"User-Agent": UA, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # Ayrshare returns a JSON error body on 4xx; surface it verbatim.
        raw = e.read().decode(errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            raise RuntimeError(f"ayrshare {e.code}: {raw[:400]}")


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode())

    def do_POST(self):
        try:
            key = _key("AYRSHARE_KEY")
            if not key:
                return self._send(500, {"ok": False, "error": "No AYRSHARE_KEY set in Vercel yet. Add it in Settings -> Environment Variables."})
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            video_url = (body.get("videoUrl") or "").strip()
            if not video_url:
                return self._send(400, {"ok": False, "error": "no videoUrl provided"})
            caps = body.get("captions") or {}
            title = (body.get("title") or "Legend").strip()
            platforms = body.get("platforms") or ["youtube", "tiktok", "instagram"]
            # One caption is used as the default post text; YouTube gets its own title.
            default_caption = caps.get("instagram") or caps.get("tiktok") or caps.get("youtube") or title
            payload = {
                "post": default_caption,
                "platforms": platforms,
                "mediaUrls": [video_url],
                "youTubeOptions": {"title": title[:95], "visibility": "public"},
                "instagramOptions": {"reels": True},
            }
            resp = _post(API, key, payload)
            # Ayrshare uses status "success" / "error"; pass the whole thing back.
            ok = str(resp.get("status", "")).lower() != "error"
            self._send(200, {"ok": ok, "result": resp})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})

    def do_GET(self):
        self._send(200, {"ok": True, "msg": "POST {videoUrl, captions, title} to publish to YouTube/TikTok/Instagram."})
