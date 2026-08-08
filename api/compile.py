"""
Vercel serverless function: compile scene images + narration into a finished MP4.

POST /api/compile
  Body: {"title": "...", "narration": "hook + script text",
         "scenes": [{"image_url": "https://..."}, ...], "voice": "en-US-ChristopherNeural"}
  -> submits a render job to JSON2Video, returns {"ok": true, "projectId": "..."}

GET /api/compile?id=<projectId>
  -> polls render status, returns {"ok": true, "status": "...", "url": "<mp4 or null>"}

Add your key in Vercel: Settings -> Environment Variables -> JSON2VIDEO_KEY
(sign up at json2video.com; free tier available).
Standard library only.
"""
import json, os, urllib.request, urllib.error, urllib.parse
from http.server import BaseHTTPRequestHandler

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
API = "https://api.json2video.com/v2/movies"


def _key(name):
    v = os.getenv(name)
    return v.strip() if v else v


def _req(url, method, key, payload=None):
    headers = {"User-Agent": UA, "Accept": "application/json", "x-api-key": key}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"json2video {e.code}: {e.read().decode(errors='replace')[:400]}")


def build_movie(title, narration, scenes, voice):
    n = max(1, len(scenes))
    words = len(narration.split()) or 1
    total = max(6, min(95, round(words / 2.4)))   # rough spoken length in seconds
    per = round(total / n, 2)
    movie_scenes = []
    for s in scenes:
        movie_scenes.append({
            "duration": per,
            "transition": {"style": "fade", "duration": 0.4},
            "elements": [{"type": "image", "src": s.get("image_url"), "zoom": 2}],
        })
    return {
        "resolution": "custom",
        "width": 1080,
        "height": 1920,
        "quality": "high",
        "scenes": movie_scenes,
        "elements": [
            {"type": "voice", "text": narration, "voice": voice, "model": "azure"},
            {"type": "subtitles"},
        ],
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode())

    def do_POST(self):
        try:
            key = _key("JSON2VIDEO_KEY")
            if not key:
                return self._send(500, {"ok": False, "error": "No JSON2VIDEO_KEY set in Vercel yet. Add it in Settings -> Environment Variables."})
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            scenes = [s for s in (body.get("scenes") or []) if s.get("image_url")]
            narration = (body.get("narration") or "").strip()
            if not scenes:
                return self._send(400, {"ok": False, "error": "no scene images provided"})
            if not narration:
                return self._send(400, {"ok": False, "error": "no narration provided"})
            voice = (body.get("voice") or "en-US-ChristopherNeural").strip()
            movie = build_movie(body.get("title") or "Legend", narration, scenes, voice)
            resp = _req(API, "POST", key, movie)
            pid = resp.get("project") or resp.get("id")
            if not pid:
                return self._send(502, {"ok": False, "error": "no project id in response", "raw": resp})
            self._send(200, {"ok": True, "projectId": pid})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})

    def do_GET(self):
        try:
            key = _key("JSON2VIDEO_KEY")
            if not key:
                return self._send(500, {"ok": False, "error": "No JSON2VIDEO_KEY set."})
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            pid = (q.get("id") or [""])[0]
            if not pid:
                return self._send(400, {"ok": False, "error": "missing id"})
            resp = _req(API + "?project=" + urllib.parse.quote(pid), "GET", key)
            movie = resp.get("movie") or resp
            self._send(200, {"ok": True, "status": movie.get("status"), "url": movie.get("url"), "message": movie.get("message")})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})
