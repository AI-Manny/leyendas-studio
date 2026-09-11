"""
Vercel serverless function: POST /api/generate
Body: {"title": "...", "premise": "...", "region": "...", "demo": false}
Returns the episode package as JSON.

Set your API key in Vercel: Project Settings -> Environment Variables -> GROQ_API_KEY
(free key from console.groq.com). OPENAI_API_KEY or ANTHROPIC_API_KEY also work.
Provider order is Groq -> OpenAI -> Anthropic (first key found); set LLM_PROVIDER
to "groq", "openai" or "anthropic" to force one when several keys are present.
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

# Model per provider. Groq retired llama-3.3-70b-versatile for free/developer
# tiers on 2026-08-16 (the catalog page still lists it; the API returns 404) and
# names openai/gpt-oss-120b as the replacement. OpenAI: gpt-4o-mini left the
# catalog; gpt-5.6-luna is the low-cost tier. Anthropic: claude-opus-5.
GROQ_MODEL = "openai/gpt-oss-120b"
OPENAI_MODEL = "gpt-5.6-luna"
ANTHROPIC_MODEL = "claude-opus-5"

# JSON Schema handed to Anthropic's output_config.format so the reply is
# guaranteed to be schema-valid JSON (no fence stripping, no retries).
EPISODE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "script": {"type": "string"},
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"beat": {"type": "string"}, "image_prompt": {"type": "string"}},
                "required": ["beat", "image_prompt"],
                "additionalProperties": False,
            },
        },
        "captions": {
            "type": "object",
            "properties": {
                "youtube": {"type": "string"},
                "tiktok": {"type": "string"},
                "instagram": {"type": "string"},
            },
            "required": ["youtube", "tiktok", "instagram"],
            "additionalProperties": False,
        },
    },
    "required": ["title", "hook", "script", "scenes", "captions"],
    "additionalProperties": False,
}


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


def _groq(system, user):
    d = _post("https://api.groq.com/openai/v1/chat/completions",
              {"Authorization": f"Bearer {_key('GROQ_API_KEY')}", "Content-Type": "application/json"},
              {"model": GROQ_MODEL,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               "temperature": 0.9, "response_format": {"type": "json_object"}})
    return d["choices"][0]["message"]["content"]


def _openai(system, user):
    # No temperature: the GPT-5 family only accepts the default sampling.
    d = _post("https://api.openai.com/v1/chat/completions",
              {"Authorization": f"Bearer {_key('OPENAI_API_KEY')}", "Content-Type": "application/json"},
              {"model": OPENAI_MODEL,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               "response_format": {"type": "json_object"}})
    return d["choices"][0]["message"]["content"]


def _anthropic(system, user):
    # Opus 5 thinks adaptively by default; structured output pins the JSON shape.
    # The server-side fallback beta re-runs a policy-declined request on another
    # model inside the same call instead of returning an empty refusal.
    d = _post("https://api.anthropic.com/v1/messages",
              {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01",
               "anthropic-beta": "server-side-fallback-2026-07-01", "Content-Type": "application/json"},
              {"model": ANTHROPIC_MODEL, "max_tokens": 4096,
               "system": system,
               "messages": [{"role": "user", "content": user}],
               "output_config": {"format": {"type": "json_schema", "schema": EPISODE_SCHEMA}},
               "fallbacks": "default"})
    if d.get("stop_reason") == "refusal":
        raise RuntimeError("the model declined this premise; rephrase it and try again")
    for block in d.get("content", []):  # skip thinking blocks, take the text
        if block.get("type") == "text":
            return block["text"]
    raise RuntimeError("empty response from Anthropic")


PROVIDERS = (("groq", "GROQ_API_KEY", _groq), ("openai", "OPENAI_API_KEY", _openai), ("anthropic", "ANTHROPIC_API_KEY", _anthropic))


def call_llm(system, user):
    """Try each configured provider in order; a failure (retired model, quota,
    outage) falls through to the next one instead of taking the feature down.
    Returns (text, provider_name), or (None, None) when no key is set."""
    forced = (_key("LLM_PROVIDER") or "").lower()
    errors = []
    for name, env, fn in PROVIDERS:
        if forced and name != forced:
            continue
        if not _key(env):
            continue
        try:
            return fn(system, user), name
        except Exception as e:  # noqa: BLE001 - surface every provider's reason
            errors.append(f"{name}: {e}")
    if errors:
        raise RuntimeError("all configured providers failed -> " + " | ".join(errors))
    return None, None  # no key -> caller falls back to demo


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
    raw, provider = call_llm(SYSTEM, USER_TEMPLATE.format(title=title, premise=premise, region=region))
    if raw is None:
        pkg = demo_package(title, premise, region)
        pkg["_warning"] = "No API key set in Vercel yet - showing demo output. Add GROQ_API_KEY to go live."
        return pkg, "demo-nokey"
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    pkg = json.loads(raw)
    pkg["_provider"] = provider  # which service wrote this one (shown nowhere yet; handy in DevTools)
    return pkg, "live"


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
