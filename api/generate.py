"""
Vercel serverless function: POST /api/generate
Body: {"title": "...", "premise": "...", "region": "...", "demo": false}
Returns the episode package as JSON.

Set your API key in Vercel: Project Settings -> Environment Variables -> GROQ_API_KEY
(free key from console.groq.com). OPENAI_API_KEY or ANTHROPIC_API_KEY also work.
Uses only the Python standard library, so there are no dependencies to install.
"""
import json, os, re, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler


def _key(name):
    """Read an env var and strip stray whitespace/newlines that break auth headers."""
    v = os.getenv(name)
    return v.strip() if v else v

SYSTEM = (
    "You are a scriptwriter for a faceless short-video channel that retells "
    "Latin American and Puerto Rican folk legends. You write vivid, ORIGINAL prose "
    "and NEVER copy sentences from any source; you retell events in your own words. "
    "Tone: cinematic, a little eerie, emotionally punchy, made to be narrated over "
    "moody visuals. Target runtime 45-60 seconds (about 120-150 spoken words). "
    "The first line must be a scroll-stopping hook. Return STRICT JSON only."
)

USER_TEMPLATE = """Legend title: {title}
Region: {region}
Factual premise (public domain; retell in your OWN words, do not copy any text): {premise}

Produce JSON with EXACTLY these keys:
{{
  "title": "a punchy video title, under 70 chars",
  "hook": "the first spoken line, designed to stop the scroll, under 120 chars",
  "script": "the full 120-150 word narration as ONE original paragraph, no headings",
  "scenes": [
    {{"beat": "one sentence describing the shot",
      "image_prompt": "detailed prompt for an AI image/video generator, cinematic, vertical 9:16, describe setting/lighting/mood, no on-screen text"}}
  ],
  "captions": {{
    "youtube": "title-style caption + 3-5 hashtags",
    "tiktok": "casual caption + 3-5 hashtags",
    "instagram": "caption + 3-5 hashtags"
  }}
}}
Aim for 5-7 scenes. Keep every field free of copyrighted text."""


def _post(url, headers, payload):
    # Send a real browser User-Agent so Cloudflare (in front of Groq) doesn't
    # flag the server-side request as a bot (Cloudflare error 1010).
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json",
        **headers,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"upstream {e.code}: {body}")


def call_llm(system, user):
    if _key("GROQ_API_KEY"):
        d = _post("https://api.groq.com/openai/v1/chat/completions",
                  {"Authorization": f"Bearer {_key('GROQ_API_KEY')}", "Content-Type": "application/json"},
                  {"model": "llama-3.3-70b-versatile",
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "temperature": 0.9, "response_format": {"type": "json_object"}})
        return d["choices"][0]["message"]["content"]
    if _key("OPENAI_API_KEY"):
        d = _post("https://api.openai.com/v1/chat/completions",
                  {"Authorization": f"Bearer {_key('OPENAI_API_KEY')}", "Content-Type": "application/json"},
                  {"model": "gpt-4o-mini",
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "temperature": 0.9, "response_format": {"type": "json_object"}})
        return d["choices"][0]["message"]["content"]
    if _key("ANTHROPIC_API_KEY"):
        d = _post("https://api.anthropic.com/v1/messages",
                  {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                  {"model": "claude-3-5-haiku-latest", "max_tokens": 1500,
                   "messages": [{"role": "user", "content": system + "\n\n" + user}]})
        return d["content"][0]["text"]
    return None  # no key -> caller falls back to demo


def demo_package(title, premise, region):
    return {
        "title": f"The Legend of {title}",
        "hook": "They told the soldiers never to speak of what happened that night.",
        "script": (f"[DEMO OUTPUT - add a GROQ_API_KEY in Vercel for real scripts.] In {region}, there is a story "
                   f"about {title}. {premise} A real ~130-word original retelling would appear here, building "
                   "tension beat by beat and ending on a line that makes viewers comment."),
        "scenes": [
            {"beat": "Establishing shot of the location at dusk.",
             "image_prompt": f"Cinematic vertical 9:16 shot of {region}, golden-hour dusk, moody fog, film grain, no text"},
            {"beat": "Close on the main figure.",
             "image_prompt": "Cinematic vertical 9:16 portrait, dramatic side lighting, historical costume, tense, no text"},
            {"beat": "The turning point.",
             "image_prompt": "Cinematic vertical 9:16, shadowy scene, cold blue moonlight, dread, no text"},
            {"beat": "The eerie aftermath.",
             "image_prompt": "Cinematic vertical 9:16, empty haunted location at night, lantern glow, no text"},
            {"beat": "Closing image that lingers.",
             "image_prompt": "Cinematic vertical 9:16, symbolic final shot, fading light, melancholic, no text"},
        ],
        "captions": {
            "youtube": f"The chilling legend of {title} \U0001F1F5\U0001F1F7 #puertorico #leyendas #folklore #history #shorts",
            "tiktok": f"the story of {title} is wild \U0001F633 #puertorico #leyenda #storytime #fyp #folklore",
            "instagram": f"{title} - a Puerto Rican legend. #puertorico #leyendas #folklore #reels #historia",
        },
    }


def build(body):
    title = (body.get("title") or "").strip() or "Untitled Legend"
    premise = (body.get("premise") or "").strip()
    region = (body.get("region") or "Puerto Rico").strip()
    if body.get("demo"):
        return demo_package(title, premise, region), "demo"
    raw = call_llm(SYSTEM, USER_TEMPLATE.format(title=title, premise=premise, region=region))
    if raw is None:
        pkg = demo_package(title, premise, region)
        pkg["_warning"] = "No API key set in Vercel yet - showing demo output. Add GROQ_API_KEY to go live."
        return pkg, "demo-nokey"
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(raw), "live"


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
            pkg, mode = build(body)
            self._send(200, {"ok": True, "mode": mode, "package": pkg})
        except Exception as e:
            self._send(500, {"ok": False, "error": str(e)})

    def do_GET(self):
        self._send(200, {"ok": True, "msg": "POST a legend here to generate an episode."})
