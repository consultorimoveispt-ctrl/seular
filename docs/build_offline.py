#!/usr/bin/env python3
"""Gera ABRIR_APP.html — o VIVAZ inteiro em UM arquivo, sem servidor e sem rede.

Estratégia (compatível com o visualizador do Arena, que bloqueia módulos
data: por CSP):
  * esbuild junta os 12 chunks JS num ÚNICO script clássico (zero import());
  * os 8 CSS ficam em tags <style> inline;
  * as 51 fotos viram data URIs resolvidas por um interceptador de <img>;
  * o estado inicial e a tela de login ficam embutidos.

Uso: python3 docs/build_offline.py
Requer esbuild (npm install esbuild) em /home/user/.local/pw.
"""
import base64
import json
import os
import re
import shutil
import subprocess

ROOT = "/home/user/vivaz"
PUB = os.path.join(ROOT, "public")
ASSETS = os.path.join(PUB, "assets")
PDIR = os.path.join(PUB, "vivaz/photos/175-vivaz")
OUT = os.path.join(ROOT, "ABRIR_APP.html")
PW = "/home/user/.local/pw"
ESBUILD = os.path.join(PW, "node_modules/.bin/esbuild")


def uri_bytes(data, mime):
    return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())


def uri_file(path, mime):
    with open(path, "rb") as fh:
        return uri_bytes(fh.read(), mime)


# --------------------------------------------------------------------------
# 1) Bundle único, sem import()
# --------------------------------------------------------------------------
SRC = "/tmp/vivaz-src"
BUNDLE = "/tmp/vivaz-bundle.js"
shutil.rmtree(SRC, ignore_errors=True)
os.makedirs(SRC)
for f in os.listdir(ASSETS):
    if f.endswith(".js"):
        shutil.copy(os.path.join(ASSETS, f), os.path.join(SRC, f))

main = os.path.join(SRC, "index-hGLYjae8.js")
text = open(main, encoding="utf-8").read()
# Neutraliza o __vitePreload: ele criaria <link> para CSS/JS (data: é
# bloqueado pelo CSP do viewer) e usa import.meta (inexistente em IIFE).
start = text.find("Y=function(e,t,n){")
assert start >= 0, "helper Y do Vite não encontrado"
i = start + len("Y=function(e,t,n)")
assert text[i] == "{"
depth, end = 0, None
for j in range(i, len(text)):
    if text[j] == "{":
        depth += 1
    elif text[j] == "}":
        depth -= 1
        if depth == 0:
            end = j + 1
            break
assert end, "fim do helper Y não encontrado"
text = text[:start] + "Y=function(e,t,n){return e()}" + text[end:]
assert "import.meta" not in text
open(main, "w", encoding="utf-8").write(text)

# O <img> do mapa nasce com um caminho absoluto; o navegador inicia o request
# antes de o MutationObserver reescrever. Resolve já na origem.
ov = os.path.join(SRC, "overview-BpF-Iopg.js")
ov_text = open(ov, encoding="utf-8").read()
ov_text = re.sub(
    r'var vt=\(\)=>`/vivaz/photos/175-vivaz/map-\$\{a\(\)\?`dark`:`light`\}\.jpg`',
    'var vt=()=>window.__VIVAZ_PHOTOS__[`map-${a()?`dark`:`light`}.jpg`]',
    ov_text)
assert "__VIVAZ_PHOTOS__[`map-" in ov_text, "patch do mapa falhou"
open(ov, "w", encoding="utf-8").write(ov_text)

subprocess.run([
    ESBUILD, main, "--bundle", "--format=iife", "--platform=browser",
    "--target=es2020", "--minify", "--outfile=" + BUNDLE,
], check=True, capture_output=True)
bundle = open(BUNDLE, encoding="utf-8").read()
assert "import(" not in bundle and "import.meta" not in bundle

# --------------------------------------------------------------------------
# 2) CSS inline e fotos
# --------------------------------------------------------------------------
css_all = []
for f in sorted(os.listdir(ASSETS)):
    if f.endswith(".css"):
        css_all.append(open(os.path.join(ASSETS, f), encoding="utf-8").read())

photos = {}
for f in sorted(os.listdir(PDIR)):
    if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        mime = "image/png" if f.endswith(".png") else "image/jpeg"
        photos[f] = uri_file(os.path.join(PDIR, f), mime)

seed = json.load(open(os.path.join(ROOT, "data/seed.json"), encoding="utf-8"))

BOOT = r"""
/* ---- VIVAZ offline: estado + fotos + login ------------------------------ */
const SEED = window.__VIVAZ_SEED__, PHOTOS = window.__VIVAZ_PHOTOS__;
const KEY = 'vivaz:br:v1', AUTH = 'vivaz:offline:auth';

const mem = new Map();
let nativeOK = false, LS;
try {
  localStorage.setItem('__p__','1'); localStorage.removeItem('__p__');
  nativeOK = true; LS = localStorage;
} catch (e) {
  LS = {
    getItem: k => mem.has(String(k)) ? mem.get(String(k)) : null,
    setItem: (k,v) => { mem.set(String(k), String(v)); },
    removeItem: k => { mem.delete(String(k)); },
    clear: () => mem.clear(),
    key: i => [...mem.keys()][i] ?? null,
    get length() { return mem.size; }
  };
  try { Object.defineProperty(window,'localStorage',{value:LS,configurable:true}); } catch(_){}
}

function resolvePhoto(v) {
  if (typeof v !== 'string' || !v.includes('/vivaz/photos/175-vivaz/')) return v;
  return PHOTOS[v.split('/vivaz/photos/175-vivaz/').pop()] || v;
}
try {
  const d = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype,'src');
  Object.defineProperty(HTMLImageElement.prototype,'src',{
    configurable:true,
    get(){ return d.get.call(this); },
    set(v){ return d.set.call(this, resolvePhoto(v)); }
  });
} catch(_){}
const setAttr = Element.prototype.setAttribute;
Element.prototype.setAttribute = function(n,v){
  if (this.tagName === 'IMG' && (n === 'src' || n === 'srcset')) v = resolvePhoto(v);
  return setAttr.call(this,n,v);
};
new MutationObserver(muts => {
  for (const m of muts) {
    if (m.type === 'attributes' && m.target.tagName === 'IMG') {
      const s = m.target.getAttribute('src');
      if (s && s.includes('/vivaz/photos/175-vivaz/')) m.target.setAttribute('src', resolvePhoto(s));
    }
    for (const n of m.addedNodes) {
      if (n.nodeType !== 1) continue;
      const list = n.tagName === 'IMG' ? [n] : n.querySelectorAll('img');
      for (const img of list) {
        const s = img.getAttribute('src');
        if (s && s.includes('/vivaz/photos/175-vivaz/')) img.setAttribute('src', resolvePhoto(s));
      }
    }
  }
}).observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['src']});

/* injeta o estado antes de o bundle ler */
let state = null;
try { state = JSON.parse(LS.getItem(KEY) || 'null'); } catch(_){}
if (!state || state.version !== 1) state = JSON.parse(JSON.stringify(SEED));
const dd = new Date(new Date().setHours(0,0,0,0));
state.seededOn = [dd.getFullYear(), dd.getMonth()+1, dd.getDate()].join('-');
LS.setItem(KEY, JSON.stringify(state));

const USERS = { 'admin@vivaz.local': 'Vivaz@2026' };
const STYLE = `
 #vivaz-gate{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;justify-content:center;
  padding:24px;background:#eef0f4;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#171a21}
 #vivaz-gate:before{content:'';position:absolute;inset:0;pointer-events:none;
  background:radial-gradient(60% 50% at 15% 10%,rgba(120,150,255,.16),transparent 70%),
             radial-gradient(50% 45% at 85% 90%,rgba(120,220,190,.14),transparent 70%)}
 #vivaz-gate .c{position:relative;width:min(420px,100%);background:#fff;border:1px solid rgba(20,25,40,.07);
  border-radius:22px;padding:34px;box-shadow:0 24px 70px rgba(25,35,60,.13)}
 #vivaz-gate .b{display:flex;align-items:center;gap:10px;font-weight:800;font-size:20px;margin-bottom:26px}
 #vivaz-gate .m{width:34px;height:34px;border-radius:10px;background:#171a21;display:grid;place-items:center}
 #vivaz-gate .m svg{width:20px;height:20px;fill:none;stroke:#fff;stroke-width:1.8;stroke-linecap:round}
 #vivaz-gate h1{margin:0 0 6px;font-size:23px} #vivaz-gate p{margin:0 0 24px;font-size:13.5px;color:#6b7280}
 #vivaz-gate label{display:block;font-size:12px;font-weight:700;color:#4b5563;margin-bottom:14px}
 #vivaz-gate input{display:block;width:100%;box-sizing:border-box;margin-top:7px;padding:12px 13px;
  font-size:14px;font-family:inherit;background:#f7f8fb;border:1px solid #e2e6ee;border-radius:11px;outline:none}
 #vivaz-gate input:focus{border-color:#3b6cf6;background:#fff}
 #vivaz-gate button{width:100%;padding:13px;border:0;border-radius:11px;cursor:pointer;background:#171a21;
  color:#fff;font:700 14px inherit;font-family:inherit}
 #vivaz-gate button:disabled{opacity:.6;cursor:default}
 #vivaz-gate .msg{min-height:18px;margin:2px 0 8px;font-size:12.5px;color:#c0392b}
 #vivaz-gate .hint{margin-top:18px;padding-top:16px;border-top:1px solid #eef0f4;font-size:11.5px;
  color:#8a93a3;text-align:center;line-height:1.6}
 #vivaz-sair{cursor:pointer}
`;
function gate(){
  let g = document.getElementById('vivaz-gate');
  if (!g) {
    const st=document.createElement('style'); st.textContent=STYLE; document.head.appendChild(st);
    g=document.createElement('div'); g.id='vivaz-gate';
    g.innerHTML=`<div class="c"><div class="b"><span class="m"><svg viewBox="0 0 24 24">
      <path d="M3.5 20.5V9.5L12 3.5l8.5 6v11"/><path d="M3.5 9.5h17M9 20.5v-6h6v6"/></svg></span>vivaz</div>
      <h1>Bem-vindo de volta</h1><p>Entre na sua conta para acessar o painel imobiliário.</p>
      <label>E-mail<input name="email" type="email" value="admin@vivaz.local"></label>
      <label>Senha<input name="password" type="password" placeholder="••••••••"></label>
      <div class="msg"></div><button type="button" data-entrar>Entrar</button>
      <div class="hint">Modo offline · <b>admin@vivaz.local</b> / <b>Vivaz@2026</b></div></div>`;
    document.body.appendChild(g);
    g.querySelector('[data-entrar]').addEventListener('click', entrar);
    g.querySelectorAll('input').forEach(i=>i.addEventListener('keydown',e=>{
      if(e.key==='Enter'){e.preventDefault();entrar();}
    }));
  }
  return g;
}
function entrar(){
  const g=document.getElementById('vivaz-gate'); if(!g) return;
  const email=g.querySelector('[name="email"]').value.trim().toLowerCase();
  const senha=g.querySelector('[name="password"]').value;
  if(USERS[email]!==senha){g.querySelector('.msg').textContent='E-mail ou senha incorretos.';return;}
  LS.setItem(AUTH,'1'); g.remove(); addLogout();
}
function addLogout(){
  let n=0;
  const t=setInterval(()=>{
    n++;
    const tools=document.querySelector('.top__tools');
    if(tools && !document.getElementById('vivaz-sair')){
      const b=document.createElement('button');
      b.type='button'; b.id='vivaz-sair'; b.className='ibtn ibtn--glass';
      b.title='Sair da conta'; b.setAttribute('aria-label','Sair da conta');
      b.innerHTML='<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5"/><path d="M15 8l4 4-4 4M19 12H9"/></svg>';
      b.addEventListener('click',()=>{LS.removeItem(AUTH);location.reload();});
      tools.appendChild(b);
    }
    if(document.getElementById('vivaz-sair')||n>25)clearInterval(t);
  },200);
}
if (LS.getItem(AUTH)==='1') addLogout(); else gate();
"""

# --------------------------------------------------------------------------
# 3) Monta o HTML
# --------------------------------------------------------------------------
html = open(os.path.join(PUB, "index.html"), encoding="utf-8").read()
html = re.sub(r'\s*<link rel="preconnect"[^>]*>', "", html)
html = re.sub(r'\s*<link href="https://fonts\.googleapis\.com[^>]*>', "", html)
html = re.sub(r'\s*<link rel="modulepreload"[^>]*>', "", html)
html = html.replace(
    '<link rel="stylesheet" crossorigin href="/assets/index-BUdVzp_j.css">',
    "<style>\n" + "\n".join(css_all) + "\n</style>")
for f, mime in (("favicon.ico", "image/x-icon"),
                ("favicon.svg", "image/svg+xml"),
                ("apple-touch-icon.png", "image/png")):
    html = html.replace("/" + f, uri_file(os.path.join(PUB, f), mime))
html = html.replace("/vivaz/photos/175-vivaz/imani-brooks-sm.jpg",
                    photos.get("imani-brooks-sm.jpg", ""))

old = '<script type="module" src="/boot.js"></script>'
assert old in html
html = html.replace(old, "")

inject = (
    "<script>window.__VIVAZ_PHOTOS__=" + json.dumps(photos, separators=(",", ":")) +
    ";window.__VIVAZ_SEED__=" + json.dumps(seed, separators=(",", ":")) +
    ";</script>\n<script>" + BOOT + "</script>\n<script>" + bundle + "</script>\n"
)
assert "</body>" in html
html = html.replace("</body>", inject + "</body>")
open(OUT, "w", encoding="utf-8").write(html)
print("gerado:", OUT, "|", len(html), "bytes | bundle", len(bundle),
      "bytes |", len(css_all), "CSS |", len(photos), "fotos | zero import()")
