import os, sys, json, wave, tempfile, subprocess, urllib.request, zipfile
from pathlib import Path
from flask import Flask, request, jsonify, Response
import argostranslate.translate

app = Flask(__name__)
LANGUAGES = {
 "en":"English","hi":"Hindi","es":"Spanish","fr":"French","de":"German",
 "it":"Italian","pt":"Portuguese","ru":"Russian","ar":"Arabic","ja":"Japanese",
 "zh":"Chinese","ko":"Korean","nl":"Dutch","tr":"Turkish","bn":"Bengali",
 "id":"Indonesian","vi":"Vietnamese","th":"Thai","pl":"Polish","sv":"Swedish"
}
BASE = Path(os.environ.get("POLYVOICE_DATA", Path.home() / ".local/share/PolyVoiceAI"))
VOICE = BASE / "vosk_models"
MODELS = {
 "en":("vosk-model-small-en-us-0.15","https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"),
 "hi":("vosk-model-small-hi-0.22","https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip")
}
_vosk = {}

def setup_voice():
    VOICE.mkdir(parents=True, exist_ok=True)
    for code,(folder,url) in MODELS.items():
        dest=VOICE/folder
        if dest.exists():
            print(LANGUAGES[code], "voice model already installed"); continue
        archive=BASE/(folder+".zip")
        print("Downloading", LANGUAGES[code], "voice model...")
        urllib.request.urlretrieve(url,archive)
        print("Extracting", LANGUAGES[code], "voice model...")
        with zipfile.ZipFile(archive) as z: z.extractall(VOICE)
        archive.unlink(missing_ok=True)
        print(LANGUAGES[code], "voice model ready")
    print("Offline English and Hindi voice models are ready.")

def get_model(code):
    if code not in MODELS: raise ValueError("Offline voice recognition supports English and Hindi only.")
    if code not in _vosk:
        from vosk import Model
        p=VOICE/MODELS[code][0]
        if not p.exists(): raise FileNotFoundError("Run: python app.py --setup")
        _vosk[code]=Model(str(p))
    return _vosk[code]

def detect(text):
    for ch in text:
        n=ord(ch)
        if 0x0900<=n<=0x097F:return "hi"
        if 0x0600<=n<=0x06FF:return "ar"
        if 0x3040<=n<=0x30FF:return "ja"
        if 0x4E00<=n<=0x9FFF:return "zh"
        if 0xAC00<=n<=0xD7AF:return "ko"
        if 0x0980<=n<=0x09FF:return "bn"
        if 0x0E00<=n<=0x0E7F:return "th"
    return "en"

def translate(text,src,dst):
    if not text.strip(): raise ValueError("Please enter text to translate.")
    if len(text)>10000: raise ValueError("Maximum text length is 10,000 characters.")
    if src=="auto": src=detect(text)
    if src not in LANGUAGES or dst not in LANGUAGES: raise ValueError("Invalid language.")
    if src==dst:return text,src
    langs={x.code:x for x in argostranslate.translate.get_installed_languages()}
    if src not in langs or dst not in langs: raise ValueError("Required language model is not installed.")
    try: return langs[src].get_translation(langs[dst]).translate(text),src
    except Exception:
        if src=="en" or dst=="en": raise ValueError(f"Model unavailable for {LANGUAGES[src]} to {LANGUAGES[dst]}.")
        try:
            middle=langs[src].get_translation(langs["en"]).translate(text)
            return langs["en"].get_translation(langs[dst]).translate(middle),src
        except Exception: raise ValueError(f"No installed translation route from {LANGUAGES[src]} to {LANGUAGES[dst]}.")

@app.get("/")
def home(): return Response(HTML,mimetype="text/html")

@app.get("/api/status")
def api_status():
    installed=argostranslate.translate.get_installed_languages()
    return jsonify(ok=True,languages=LANGUAGES,installed_codes=[x.code for x in installed],voice_languages=["en","hi"])

@app.post("/api/translate")
def api_translate():
    d=request.get_json(silent=True) or {}
    try:
        result,detected=translate(str(d.get("text","")),str(d.get("source","auto")),str(d.get("target","hi")))
        return jsonify(ok=True,translated=result,detected=detected)
    except Exception as e:return jsonify(ok=False,error=str(e)),400

@app.post("/api/transcribe")
def transcribe():
    srcfile=wavfile=None
    try:
        from vosk import KaldiRecognizer
        import imageio_ffmpeg
        if "audio" not in request.files: raise ValueError("No audio received.")
        language=request.form.get("language","en")
        model=get_model(language)
        with tempfile.NamedTemporaryFile(delete=False,suffix=".webm") as f:
            srcfile=f.name; request.files["audio"].save(srcfile)
        wavfile=tempfile.mktemp(suffix=".wav")
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),"-y","-i",srcfile,"-ar","16000","-ac","1","-f","wav",wavfile],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        with wave.open(wavfile,"rb") as wf:
            rec=KaldiRecognizer(model,wf.getframerate()); pieces=[]
            while True:
                data=wf.readframes(4000)
                if not data:break
                if rec.AcceptWaveform(data):pieces.append(json.loads(rec.Result()).get("text",""))
            pieces.append(json.loads(rec.FinalResult()).get("text",""))
        return jsonify(ok=True,text=" ".join(x for x in pieces if x).strip())
    except Exception as e:return jsonify(ok=False,error=str(e)),400
    finally:
        for p in (srcfile,wavfile):
            if p and os.path.exists(p):
                try:os.remove(p)
                except OSError:pass

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PolyVoice AI - Offline Translation Studio</title>
<style>
*{box-sizing:border-box}body{margin:0;padding:25px 14px;background:#f2f5fc;color:#1c2940;font-family:Segoe UI,Arial}
main{max-width:950px;margin:auto}.head{text-align:center;margin:12px 0 25px}h1{color:#304baf;margin:0;font-size:34px}
.sub{color:#68748c;margin-top:8px}.panel{background:white;padding:22px;border-radius:18px;box-shadow:0 8px 30px #182b5015}
.controls{display:grid;grid-template-columns:1fr auto 1fr;gap:12px;align-items:end}
label{display:block;font-weight:650;margin-bottom:7px;font-size:14px}
select,textarea{width:100%;border:1px solid #d5ddeb;border-radius:10px;padding:12px;font:inherit;background:white}
textarea{height:185px;resize:vertical;margin-top:8px}.editors{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:18px}
button{border:0;border-radius:10px;padding:12px 17px;font-weight:650;cursor:pointer}
.primary{background:#3557d5;color:white}.secondary,.swap{background:#edf1ff;color:#304baf}
.swap{font-size:20px}.actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:13px}
.status{margin-top:15px;min-height:22px;color:#58657d}.note{font-size:12px;color:#778198;line-height:1.5;margin-top:15px}
@media(max-width:650px){.editors{grid-template-columns:1fr}h1{font-size:27px}}
</style></head><body><main>
<header class="head"><h1>🌐 PolyVoice AI</h1><div class="sub">Multilingual Offline Translation Studio</div></header>
<section class="panel">
<div class="controls"><div><label for="source">Translate from</label><select id="source"><option value="auto">Auto Detect</option></select></div>
<button class="swap" id="swap">⇄</button><div><label for="target">Translate to</label><select id="target"></select></div></div>
<div class="editors"><div><label for="input">Enter text</label><textarea id="input" placeholder="Type or record your text..."></textarea>
<div class="actions"><button class="secondary" id="mic">🎙 Speak</button><button class="secondary" id="clear">Clear</button></div></div>
<div><label for="output">Translation</label><textarea id="output" readonly placeholder="Translation appears here..."></textarea>
<div class="actions"><button class="secondary" id="speak">🔊 Listen</button><button class="secondary" id="copy">Copy</button></div></div></div>
<div class="actions"><button class="primary" id="go">Translate</button></div>
<div class="status" id="status">Ready. Translation uses local Argos models.</div>
<div class="note">Offline translation requires installed language models. Offline microphone recognition supports English and Hindi only. Speech playback uses voices available on your computer/browser. First-time model setup requires internet.</div>
</section></main>
<script>
const LANGS=__LANGS__,src=document.getElementById('source'),dst=document.getElementById('target'),msg=document.getElementById('status');
for(const [c,n] of Object.entries(LANGS)){src.add(new Option(n,c));dst.add(new Option(n,c))}
src.value='auto';dst.value='hi';const say=t=>msg.textContent=t;
document.getElementById('go').onclick=async()=>{
 let text=document.getElementById('input').value;if(!text.trim())return say('Please enter text first.');
 let b=document.getElementById('go');b.disabled=true;say('Translating locally...');
 try{let r=await fetch('/api/translate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,source:src.value,target:dst.value})});
 let d=await r.json();if(!r.ok||!d.ok)throw Error(d.error);document.getElementById('output').value=d.translated;say('Translation complete. Detected: '+LANGS[d.detected]);}
 catch(e){say(e.message||'Translation failed.')}finally{b.disabled=false}
};
document.getElementById('swap').onclick=()=>{if(src.value==='auto')return say('Select a source language first.');let x=src.value;src.value=dst.value;dst.value=x};
document.getElementById('clear').onclick=()=>{document.getElementById('input').value='';document.getElementById('output').value='';say('Cleared.')};
document.getElementById('copy').onclick=async()=>{let t=document.getElementById('output').value;if(!t)return say('Nothing to copy.');await navigator.clipboard.writeText(t);say('Copied.')};
document.getElementById('speak').onclick=()=>{let t=document.getElementById('output').value;if(!t)return say('Nothing to play.');if(!window.speechSynthesis)return say('Speech playback unavailable.');speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(t);u.lang=dst.value;speechSynthesis.speak(u)};
let rec,chunks=[];
document.getElementById('mic').onclick=async()=>{
 let b=document.getElementById('mic');if(rec&&rec.state==='recording'){rec.stop();b.textContent='🎙 Speak';return}
 if(!['en','hi'].includes(src.value))return say('Select English or Hindi for offline voice input.');
 try{let stream=await navigator.mediaDevices.getUserMedia({audio:true});rec=new MediaRecorder(stream);chunks=[];
 rec.ondataavailable=e=>{if(e.data.size)chunks.push(e.data)};
 rec.onstop=async()=>{stream.getTracks().forEach(t=>t.stop());say('Converting speech to text...');
 let f=new FormData();f.append('audio',new Blob(chunks,{type:chunks[0]?.type||'audio/webm'}),'recording.webm');f.append('language',src.value);
 try{let r=await fetch('/api/transcribe',{method:'POST',body:f}),d=await r.json();if(!r.ok||!d.ok)throw Error(d.error);document.getElementById('input').value=d.text;say(d.text?'Voice recognized.':'No speech detected.')}
 catch(e){say(e.message)}};
 rec.start();b.textContent='■ Stop';say('Recording... press Stop when finished.');
 }catch(e){say('Microphone error: '+e.message)}
};
</script></body></html>'''.replace("__LANGS__",json.dumps(LANGUAGES,ensure_ascii=False))

if __name__=="__main__":
    if "--setup" in sys.argv: setup_voice()
    else:
        print("\\n==============================================")
        print(" POLYVOICE AI - LOCAL TRANSLATION STUDIO")
        print(" Open: http://127.0.0.1:5000")
        print(" Press CTRL+C to stop")
        print("==============================================\\n")
        app.run(host="127.0.0.1",port=5000,debug=False)

