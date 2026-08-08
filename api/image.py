"""
Vercel serverless function: POST /api/image
Body: {"prompt": "a scene image prompt"}
Returns {"ok": true, "url": "https://..."} with a generated vertical (9:16) image.

Uses fal.ai's flux/schnell model — fast and very cheap (about a cent an image).
Add your key in Vercel: Settings -> Environment Variables -> FAL_KEY
(get it free at fal.ai; pay-as-you-go, no monthly fee).
Standard library only, no dependencies.
"""
import json, os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")


def _key(name):
    v = os.getenv(name)
    return v.strip() if v else v


def _post(url, headers, payload):
    headers = {"User-Agent": UA, "Accept": "application/json", **headers}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"upstream {e.code}: {e.read().decode(errors='replace')[:300]}")


def gen_image(prompt):
    key = _key("FAL_KEY")
    if not key:
        raise RuntimeError("No FAL_KEY set in Vercel yet. Add it in Settings -> Environment Variables to enable images.")
    d = _post(
        "https://fal.run/fal-ai/flux/schnell",
        {"Authorization": f"Key {key}", "Content-Type": "application/json"},
        {"prompt": prompt, "image_size": "portrait_16_9", "num_images": 1, "num_inference_steps": 4},
    )
    imgs = d.get("images") or []
    if not imgs:
        raise RuntimeError("no image returned")
    return imgs[0]["url"]


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode())

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            prompt = (body.get("prompt") or "").strip()
            if not prompt:
                return self._send(400, {"ok": False, "error": "missing prompt"})
            url = gen_image(prompt)
            self._send(200, {"ok": True, "url": url})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})

    def do_GET(self):
        self._send(200, {"ok": True, "msg": "POST {prompt} to generate a 9:16 image."})
