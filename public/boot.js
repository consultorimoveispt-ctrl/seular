/* VIVAZ — autenticação + persistência, à prova de iframe.
 *
 * Os bundles originais em /assets continuam intactos. Este arquivo:
 *   1) exige login antes de carregar o app;
 *   2) faz o estado 'vivaz:br:v1' ser lido/gravado no banco via /api/state.
 *
 * O Live Preview do Arena incorpora o app num iframe de outra origem, onde
 * cookies de terceiros são bloqueados e localStorage pode ser inacessível.
 * Por isso usamos token Bearer (não cookie) e um storage com fallback em
 * memória. A interface renderizada continua exatamente a mesma.
 */
(() => {
  const KEY = 'vivaz:br:v1';
  const TOKEN_KEY = 'vivaz:token';

  // ---- storage seguro (funciona mesmo em iframe com origem opaca) ---------
  const memory = new Map();
  let nativeOK = false;
  let LS;
  try {
    window.localStorage.setItem('__vivaz_probe__', '1');
    window.localStorage.removeItem('__vivaz_probe__');
    nativeOK = true;
    LS = window.localStorage;
  } catch (error) {
    LS = {
      getItem: (k) => (memory.has(String(k)) ? memory.get(String(k)) : null),
      setItem: (k, v) => { memory.set(String(k), String(v)); },
      removeItem: (k) => { memory.delete(String(k)); },
      clear: () => memory.clear(),
      key: (i) => [...memory.keys()][i] ?? null,
      get length() { return memory.size; }
    };
    try {
      Object.defineProperty(window, 'localStorage', {
        value: LS, configurable: true, writable: true
      });
    } catch (_) { /* o app usa try/catch ao acessar localStorage */ }
  }

  const shimSet = nativeOK ? null : LS.setItem.bind(LS);
  const rawSet = nativeOK
    ? (k, v) => Storage.prototype.setItem.call(LS, k, v)
    : (k, v) => shimSet(k, v);

  // ---- carteira vazia: estado visual decente no carrossel ----------------
  // O app original sempre assume que existe um imóvel em destaque; com zero
  // imóveis sobra um retângulo cinza. Sem alterar os bundles, escondemos esse
  // placeholder só enquanto a carteira estiver vazia.
  const EMPTY_CSS = `
    html.vivaz-vazio #ov-hero{background:#fff;overflow:hidden}
    html.vivaz-vazio #ov-hero > *{display:none!important}
    html.vivaz-vazio #ov-hero::before{content:'';position:absolute;inset:0;
      background:radial-gradient(62% 42% at 50% 32%,rgba(96,130,240,.10),transparent 72%)}
    html.vivaz-vazio #ov-hero::after{
      content:'Nenhum imóvel em destaque ainda\\A Use “+ Novo imóvel” para cadastrar o primeiro';
      position:absolute;inset:0;display:grid;place-content:center;text-align:center;
      white-space:pre;padding:30px;color:#727b8c;
      font:600 14px/2 'Plus Jakarta Sans',system-ui,-apple-system,Segoe UI,sans-serif}
    html[data-theme="dark"].vivaz-vazio #ov-hero{background:#1c2230}
  `;
  try {
    const st = document.createElement('style');
    st.textContent = EMPTY_CSS;
    (document.head || document.documentElement).appendChild(st);
  } catch (_) {}

  function syncEmpty(raw) {
    try {
      const s = JSON.parse(raw || '{}');
      document.documentElement.classList.toggle(
        'vivaz-vazio', Array.isArray(s.properties) && s.properties.length === 0);
    } catch (_) { /* ignore */ }
  }

  let TOKEN = '';
  try { TOKEN = LS.getItem(TOKEN_KEY) || ''; } catch (_) { TOKEN = ''; }

  // ---- fotos servidas pelo Supabase Storage -------------------------------
  // O bundle original monta os src como "/vivaz/photos/175-vivaz/<arquivo>".
  // Quando o backend Supabase injeta __VIVAZ_PHOTO_BASE__, reescrevemos no
  // momento da atribuição (sem tocar nos bundles originais). Em modo SQLite
  // a base fica vazia e as fotos continuam locais.
  const PHOTO_BASE = window.__VIVAZ_PHOTO_BASE__ || '';
  const PHOTO_MARK = '/vivaz/photos/175-vivaz/';

  function photoURL(value) {
    if (!PHOTO_BASE || typeof value !== 'string') return value;
    if (!value.includes(PHOTO_MARK)) return value;
    if (/^(https?:|data:|blob:)/i.test(value)) return value;
    const name = value.split(PHOTO_MARK).pop().split(/[?#]/)[0];
    return PHOTO_BASE + name;
  }

  if (PHOTO_BASE) {
    try {
      const srcDesc = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');
      Object.defineProperty(HTMLImageElement.prototype, 'src', {
        configurable: true,
        get() { return srcDesc.get.call(this); },
        set(v) { return srcDesc.set.call(this, photoURL(v)); }
      });
      const origSetAttr = Element.prototype.setAttribute;
      Element.prototype.setAttribute = function (name, value) {
        if (this.tagName === 'IMG' && (name === 'src' || name === 'srcset')) {
          value = photoURL(value);
        }
        return origSetAttr.call(this, name, value);
      };
      // innerHTML não passa por setAttribute: cobre esses nós também.
      new MutationObserver((muts) => {
        for (const m of muts) {
          const nodes = [];
          if (m.type === 'attributes' && m.target.tagName === 'IMG') nodes.push(m.target);
          for (const n of m.addedNodes) {
            if (n.nodeType !== 1) continue;
            if (n.tagName === 'IMG') nodes.push(n);
            else if (n.querySelectorAll) nodes.push(...n.querySelectorAll('img'));
          }
          for (const img of nodes) {
            const s = img.getAttribute('src');
            if (s && s.includes(PHOTO_MARK) && !s.startsWith(PHOTO_BASE)) {
              img.setAttribute('src', photoURL(s));
            }
          }
        }
      }).observe(document.documentElement, {
        subtree: true, childList: true, attributes: true,
        attributeFilter: ['src']
      });
    } catch (_) { /* navegador sem MutationObserver: mantém fotos locais */ }
  }

  // ---- cliente HTTP ------------------------------------------------------
  function api(path, options) {
    const opts = options || {};
    const headers = Object.assign({}, opts.headers || {});
    if (TOKEN) headers['Authorization'] = 'Bearer ' + TOKEN;
    if (opts.body && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    return fetch(path, Object.assign({}, opts, {
      headers, credentials: 'omit'
    }));
  }
  // O painel de administração reaproveita este cliente (mesmo token Bearer).
  window.__VIVAZ_API__ = api;

  // ---- sincronismo do estado com o banco ---------------------------------
  let pending = null;
  let timer = null;

  function onSet(key, value) {
    if (key !== KEY) return;
    pending = String(value);
    syncEmpty(pending);
    clearTimeout(timer);
    timer = setTimeout(flush, 250);
  }

  if (nativeOK) {
    const protoSet = Storage.prototype.setItem;
    Storage.prototype.setItem = function (key, value) {
      const result = protoSet.call(this, key, value);
      onSet(key, value);
      return result;
    };
  } else {
    LS.setItem = function (key, value) {
      const result = shimSet(key, value);
      onSet(key, value);
      return result;
    };
  }

  function flush() {
    if (pending === null) return;
    const body = pending;
    pending = null;
    api('/api/state', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body
    })
      .then((r) => {
        if (r.status === 401) {
          TOKEN = '';
          try { LS.removeItem(TOKEN_KEY); } catch (_) {}
          showLogin('Sessão expirada. Entre novamente.');
        }
      })
      .catch(() => { pending = body; });
  }

  window.addEventListener('beforeunload', () => {
    let raw = pending;
    if (!raw) { try { raw = LS.getItem(KEY); } catch (_) { raw = null; } }
    if (raw) {
      api('/api/state', {
        method: 'PUT', keepalive: true,
        headers: { 'Content-Type': 'application/json' }, body: raw
      });
    }
  });

  // ---- tela de login -----------------------------------------------------
  const STYLE = `
    #vivaz-gate{position:fixed;inset:0;z-index:99999;display:flex;align-items:center;
      justify-content:center;padding:24px;background:#eef0f4;
      font-family:'Plus Jakarta Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#171a21}
    #vivaz-gate:before{content:'';position:absolute;inset:0;pointer-events:none;
      background:radial-gradient(60% 50% at 15% 10%,rgba(120,150,255,.16),transparent 70%),
                 radial-gradient(50% 45% at 85% 90%,rgba(120,220,190,.14),transparent 70%)}
    #vivaz-gate .vg-card{position:relative;width:min(420px,100%);background:#fff;
      border:1px solid rgba(20,25,40,.07);border-radius:22px;padding:34px 34px 28px;
      box-shadow:0 24px 70px rgba(25,35,60,.13)}
    #vivaz-gate .vg-brand{display:flex;align-items:center;gap:10px;font-weight:800;
      font-size:20px;letter-spacing:-.03em;margin-bottom:26px}
    #vivaz-gate .vg-mark{width:34px;height:34px;border-radius:10px;background:#171a21;
      display:grid;place-items:center}
    #vivaz-gate .vg-mark svg{width:20px;height:20px;fill:none;stroke:#fff;
      stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
    #vivaz-gate h1{margin:0 0 6px;font-size:23px;letter-spacing:-.03em}
    #vivaz-gate p{margin:0 0 24px;font-size:13.5px;color:#6b7280;line-height:1.55}
    #vivaz-gate label{display:block;font-size:12px;font-weight:700;color:#4b5563;margin-bottom:14px}
    #vivaz-gate input{display:block;width:100%;box-sizing:border-box;margin-top:7px;
      padding:12px 13px;font-size:14px;font-family:inherit;color:#171a21;background:#f7f8fb;
      border:1px solid #e2e6ee;border-radius:11px;outline:none;transition:.18s}
    #vivaz-gate input:focus{border-color:#3b6cf6;background:#fff;
      box-shadow:0 0 0 3px rgba(59,108,246,.13)}
    #vivaz-gate button{width:100%;padding:13px;border:0;border-radius:11px;cursor:pointer;
      background:#171a21;color:#fff;font:700 14px inherit;font-family:inherit;transition:.18s}
    #vivaz-gate button:hover{background:#33394a}
    #vivaz-gate button:disabled{opacity:.6;cursor:default}
    #vivaz-gate .vg-msg{min-height:18px;margin:2px 0 8px;font-size:12.5px;color:#c0392b}
    #vivaz-gate .vg-hint{margin-top:18px;padding-top:16px;border-top:1px solid #eef0f4;
      font-size:11.5px;color:#8a93a3;text-align:center;line-height:1.6}
    #vivaz-gate .vg-hint b{color:#4b5563;font-weight:700}
    #vivaz-sair{cursor:pointer}
  `;

  const MARKUP = `
    <div class="vg-card">
      <div class="vg-brand">
        <span class="vg-mark"><svg viewBox="0 0 24 24">
          <path d="M3.5 20.5V9.5L12 3.5l8.5 6v11"/><path d="M3.5 9.5h17M9 20.5v-6h6v6"/>
        </svg></span><span>vivaz</span>
      </div>
      <h1>Bem-vindo de volta</h1>
      <p>Entre na sua conta para acessar o painel imobiliário.</p>
      <div class="vg-form">
        <label>E-mail
          <input name="email" type="email" autocomplete="username"
                 value="admin@vivaz.local" /></label>
        <label>Senha
          <input name="password" type="password" autocomplete="current-password"
                 placeholder="••••••••" /></label>
        <div class="vg-msg" data-msg></div>
        <button type="button" data-entrar>Entrar</button>
      </div>
      <div class="vg-hint">Acesso inicial: <b>admin@vivaz.local</b> · <b>Vivaz@2026</b></div>
    </div>
  `;

  function showLogin(message) {
    let gate = document.getElementById('vivaz-gate');
    if (!gate) {
      const style = document.createElement('style');
      style.textContent = STYLE;
      document.head.appendChild(style);
      gate = document.createElement('div');
      gate.id = 'vivaz-gate';
      gate.innerHTML = MARKUP;
      document.body.appendChild(gate);
      // IMPORTANTE: o preview do Arena é um iframe com sandbox="allow-scripts"
      // (sem allow-forms). Um <form> com type="submit" é bloqueado pelo Chrome
      // antes de qualquer JS rodar — por isso usamos botão comum + click.
      gate.querySelector('[data-entrar]').addEventListener('click', onSubmit);
      gate.querySelectorAll('input').forEach((input) => {
        input.addEventListener('keydown', (event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            onSubmit(event);
          }
        });
      });
    }
    gate.style.display = 'flex';
    gate.querySelector('[data-msg]').textContent = message || '';
    const field = gate.querySelector('input[name="password"]');
    if (field) field.focus();
  }

  async function onSubmit(event) {
    if (event && event.preventDefault) event.preventDefault();
    const gate = document.getElementById('vivaz-gate');
    if (!gate) return;
    const button = gate.querySelector('[data-entrar]');
    if (button.disabled) return;
    button.disabled = true;
    button.textContent = 'Entrando...';
    try {
      const response = await api('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: gate.querySelector('input[name="email"]').value,
          password: gate.querySelector('input[name="password"]').value
        })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        showLogin(data.error || 'Não foi possível entrar.');
        return;
      }
      TOKEN = data.token || '';
      if (TOKEN) rawSet(TOKEN_KEY, TOKEN);
      await start();
    } catch (error) {
      showLogin('Sem conexão com o servidor. Recarregue o preview ou peça para reiniciá-lo.');
    } finally {
      button.disabled = false;
      button.textContent = 'Entrar';
    }
  }

  function addLogout() {
    let tries = 0;
    const interval = setInterval(() => {
      tries += 1;
      const tools = document.querySelector('.top__tools');
      if (tools && !document.getElementById('vivaz-sair')) {
        const button = document.createElement('button');
        button.type = 'button';
        button.id = 'vivaz-sair';
        button.className = 'ibtn ibtn--glass';
        button.title = 'Sair da conta';
        button.setAttribute('aria-label', 'Sair da conta');
        button.innerHTML = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">' +
          '<path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5"/>' +
          '<path d="M15 8l4 4-4 4M19 12H9"/></svg>';
        button.addEventListener('click', async () => {
          try { await api('/api/logout', { method: 'POST' }); } catch (_) {}
          TOKEN = '';
          try { LS.removeItem(TOKEN_KEY); } catch (_) {}
          location.reload();
        });
        tools.appendChild(button);
      }
      if (document.getElementById('vivaz-sair') || tries > 25) clearInterval(interval);
    }, 200);
  }

  async function start() {
    let health;
    try {
      health = await api('/api/health');
    } catch (error) {
      showLogin('Servidor indisponível. Recarregue a página ou peça para reiniciar o preview.');
      return;
    }
    if (!health.ok) {
      showLogin('Servidor respondeu com erro ' + health.status + '.');
      return;
    }

    const session = await api('/api/session')
      .then((r) => r.json())
      .catch(() => ({ authenticated: false }));
    if (!session.authenticated) {
      showLogin(TOKEN ? 'Sessão não confirmada. Tente entrar novamente.' : '');
      return;
    }
    window.__VIVAZ_USER__ = session.user;

    let payload = { state: null };
    try {
      payload = await (await api('/api/state')).json();
    } catch (error) { /* primeira execução: o app semeia o próprio estado */ }

    if (payload.state && typeof payload.state === 'object') {
      const state = Object.assign({}, payload.state);
      const today = new Date(new Date().setHours(0, 0, 0, 0));
      state.seededOn = [today.getFullYear(), today.getMonth() + 1,
                        today.getDate()].join('-');
      rawSet(KEY, JSON.stringify(state));
      syncEmpty(JSON.stringify(state));
    } else {
      try { LS.removeItem(KEY); } catch (_) {}
      document.documentElement.classList.remove('vivaz-vazio');
    }

    const gate = document.getElementById('vivaz-gate');
    if (gate) gate.remove();

    await import('/assets/index-hGLYjae8.js');
    addLogout();
    // Painel de equipe: rota nova, sem alterar nenhuma das 7 telas originais.
    if (session.user && session.user.role === 'admin') {
      try { await import('/admin.js'); } catch (_) { /* opcional */ }
    }
  }

  start();
})();
