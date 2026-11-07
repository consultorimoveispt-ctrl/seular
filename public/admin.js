/* VIVAZ · Painel de administração (carregado só para role=admin).
 * Usa o mesmo cliente HTTP do boot.js, portanto o mesmo token Bearer.
 * Não altera nenhuma das 7 telas originais: é um overlay independente.
 */
(() => {
  const api = window.__VIVAZ_API__;
  const ME = window.__VIVAZ_USER__ || {};
  if (!api || ME.role !== 'admin') return;

  const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
  const n = (v) => Number(v || 0).toLocaleString('pt-BR');

  const CSS = `
    #vivaz-admin-btn{cursor:pointer}
    #vivaz-admin{position:fixed;inset:0;z-index:99998;display:none;
      align-items:flex-start;justify-content:center;padding:32px 20px;
      overflow:auto;background:rgba(18,22,34,.46);backdrop-filter:blur(5px);
      font-family:'Plus Jakarta Sans',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:#171a21}
    #vivaz-admin.on{display:flex}
    #vivaz-admin .va-box{width:min(1080px,100%);background:#fff;border-radius:22px;
      box-shadow:0 30px 90px rgba(15,22,40,.28);overflow:hidden;margin:auto 0}
    #vivaz-admin .va-head{display:flex;align-items:flex-start;justify-content:space-between;
      gap:16px;padding:26px 30px 20px;border-bottom:1px solid #eef0f4}
    #vivaz-admin h2{margin:0 0 5px;font-size:20px;letter-spacing:-.03em}
    #vivaz-admin .va-sub{margin:0;font-size:12.5px;color:#727b8c;line-height:1.5}
    #vivaz-admin .va-x{width:34px;height:34px;flex:none;border:0;border-radius:10px;
      background:#f3f5f9;cursor:pointer;font-size:19px;color:#4b5563}
    #vivaz-admin .va-body{padding:22px 30px 30px}
    #vivaz-admin .va-kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:22px}
    #vivaz-admin .va-kpi{background:#f7f8fb;border:1px solid #eef0f4;border-radius:14px;padding:14px}
    #vivaz-admin .va-kpi b{display:block;font-size:21px;letter-spacing:-.04em}
    #vivaz-admin .va-kpi span{font-size:11px;color:#7b8494}
    #vivaz-admin h3{margin:24px 0 12px;font-size:13px;text-transform:uppercase;
      letter-spacing:.09em;color:#6b7280}
    #vivaz-admin table{width:100%;border-collapse:collapse;font-size:12.5px}
    #vivaz-admin th{text-align:left;padding:9px 10px;color:#8a93a3;font-weight:700;
      font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #eef0f4}
    #vivaz-admin td{padding:11px 10px;border-bottom:1px solid #f3f5f9;vertical-align:middle}
    #vivaz-admin .va-who{display:flex;align-items:center;gap:10px}
    #vivaz-admin .va-av{width:32px;height:32px;flex:none;border-radius:50%;background:#171a21;
      color:#fff;display:grid;place-items:center;font-size:12px;font-weight:800}
    #vivaz-admin .va-who b{display:block;font-size:12.5px}
    #vivaz-admin .va-who small{display:block;color:#8a93a3;font-size:11px}
    #vivaz-admin select,#vivaz-admin input{font:inherit;font-size:12px;padding:7px 9px;
      border:1px solid #dfe4ed;border-radius:9px;background:#fff;color:#171a21;outline:none}
    #vivaz-admin select:focus,#vivaz-admin input:focus{border-color:#3b6cf6;
      box-shadow:0 0 0 3px rgba(59,108,246,.12)}
    #vivaz-admin .va-pill{display:inline-block;padding:4px 9px;border-radius:20px;
      font-size:10.5px;font-weight:700}
    #vivaz-admin .va-pill.on{background:#e6f7ee;color:#16794a}
    #vivaz-admin .va-pill.off{background:#fdecec;color:#b4232c}
    #vivaz-admin button.va-a{border:0;background:#f1f3f8;border-radius:9px;padding:7px 10px;
      font:inherit;font-size:11.5px;font-weight:700;color:#3c4557;cursor:pointer;margin-right:5px}
    #vivaz-admin button.va-a:hover{background:#e5e9f2}
    #vivaz-admin button.va-a.pri{background:#171a21;color:#fff}
    #vivaz-admin .va-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
    #vivaz-admin .va-card{background:#f7f8fb;border:1px solid #eef0f4;border-radius:16px;padding:18px}
    #vivaz-admin .va-card label{display:block;font-size:11px;font-weight:700;color:#5b6474;margin:0 0 11px}
    #vivaz-admin .va-card input,#vivaz-admin .va-card select{width:100%;box-sizing:border-box;margin-top:5px}
    #vivaz-admin .va-row{display:flex;gap:8px;align-items:center;margin-top:11px;flex-wrap:wrap}
    #vivaz-admin .va-msg{min-height:18px;margin:9px 0 0;font-size:12px;font-weight:600}
    #vivaz-admin .va-msg.ok{color:#16794a} #vivaz-admin .va-msg.erro{color:#b4232c}
    #vivaz-admin .va-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
    #vivaz-admin .va-chip{background:#fff;border:1px solid #e6eaf2;border-radius:9px;
      padding:6px 10px;font-size:11.5px}
    #vivaz-admin .va-chip b{font-size:13px}
    #vivaz-admin .va-foot{font-size:11px;color:#9aa3b2;padding:14px 30px 20px;border-top:1px solid #eef0f4}
    @media(max-width:820px){#vivaz-admin .va-kpis{grid-template-columns:repeat(2,1fr)}
      #vivaz-admin .va-grid{grid-template-columns:1fr}#vivaz-admin table{font-size:11px}}
    [data-theme="dark"] #vivaz-admin .va-box{background:#1c2230;color:#e7eaf2}
    [data-theme="dark"] #vivaz-admin .va-card,[data-theme="dark"] #vivaz-admin .va-kpi{background:#242b3a;border-color:#313a4c}
    [data-theme="dark"] #vivaz-admin input,[data-theme="dark"] #vivaz-admin select{background:#141a26;border-color:#3a4457;color:#e7eaf2}
    [data-theme="dark"] #vivaz-admin .va-head,[data-theme="dark"] #vivaz-admin .va-foot,
    [data-theme="dark"] #vivaz-admin td,[data-theme="dark"] #vivaz-admin th{border-color:#313a4c}
  `;

  const style = document.createElement('style');
  style.textContent = CSS;
  document.head.appendChild(style);

  // ---- botão na barra superior (espera o app montar) ---------------------
  let tentativas = 0;
  const iv = setInterval(() => {
    tentativas += 1;
    const tools = document.querySelector('.top__tools');
    if (tools && !document.getElementById('vivaz-admin-btn')) {
      const btn = document.createElement('button');
      btn.type = 'button'; btn.id = 'vivaz-admin-btn';
      btn.className = 'ibtn ibtn--glass';
      btn.title = 'Equipe e carteiras';
      btn.setAttribute('aria-label', 'Equipe e carteiras');
      btn.innerHTML = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">' +
        '<path d="M16 20v-1.5a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4V20"/>' +
        '<circle cx="9" cy="7" r="3.2"/><path d="M22 20v-1.5a4 4 0 0 0-3-3.87"/>' +
        '<path d="M16.5 4.2a3.2 3.2 0 0 1 0 6.1"/></svg>';
      btn.addEventListener('click', abrir);
      tools.insertBefore(btn, tools.querySelector('#vivaz-sair') || null);
    }
    if (document.getElementById('vivaz-admin-btn') || tentativas > 30) clearInterval(iv);
  }, 200);

  const root = document.createElement('div');
  root.id = 'vivaz-admin';
  root.innerHTML = `
    <div class="va-box" role="dialog" aria-modal="true" aria-label="Equipe e carteiras">
      <div class="va-head">
        <div><h2>Equipe e carteiras</h2>
          <p class="va-sub">Cada usuário tem sua própria carteira — imóveis, clientes, negócios e financeiro — isolada por RLS no Postgres. Como administrador, você supervisiona todas.</p></div>
        <button class="va-x" type="button" data-fechar aria-label="Fechar">×</button>
      </div>
      <div class="va-body">
        <div class="va-kpis" id="va-kpis"></div>
        <h3>Usuários</h3>
        <table><thead><tr>
          <th>Usuário</th><th>Papel</th><th>Status</th><th>Carteira</th><th>Ações</th>
        </tr></thead><tbody id="va-linhas"></tbody></table>
        <div class="va-grid">
          <div class="va-card">
            <h3 style="margin-top:0">Novo usuário</h3>
            <label>Nome<input id="va-n-nome" placeholder="Nome completo" /></label>
            <label>E-mail<input id="va-n-email" type="email" placeholder="corretor@imobiliaria.com.br" /></label>
            <label>Senha inicial<input id="va-n-senha" type="password" placeholder="mínimo 8 caracteres" /></label>
            <label>Papel<select id="va-n-role">
              <option value="corretor">Corretor</option><option value="gerente">Gerente</option>
              <option value="admin">Administrador</option></select></label>
            <div class="va-row"><button class="va-a pri" type="button" data-criar>Criar usuário</button></div>
            <p class="va-msg" id="va-msg-novo"></p>
          </div>
          <div class="va-card">
            <h3 style="margin-top:0">Minha conta</h3>
            <label>Nome<input id="va-p-nome" /></label>
            <label>Telefone<input id="va-p-phone" placeholder="+55 (21) 99999-9999" /></label>
            <div class="va-row"><button class="va-a" type="button" data-perfil>Salvar perfil</button></div>
            <label style="margin-top:14px">Senha atual<input id="va-s-atual" type="password" /></label>
            <label>Nova senha<input id="va-s-nova" type="password" placeholder="mínimo 8 caracteres" /></label>
            <div class="va-row"><button class="va-a" type="button" data-senha>Trocar senha</button></div>
            <p class="va-msg" id="va-msg-perfil"></p>
          </div>
        </div>
        <div class="va-grid" style="margin-top:18px">
          <div class="va-card">
            <h3 style="margin-top:0">Ver carteira de um usuário</h3>
            <label>Usuário<select id="va-ver-user"></select></label>
            <div class="va-row"><button class="va-a" type="button" data-ver>Consultar</button></div>
            <div class="va-chips" id="va-chips"></div>
          </div>
          <div class="va-card">
            <h3 style="margin-top:0">Redefinir senha de um usuário</h3>
            <label>Usuário<select id="va-r-user"></select></label>
            <label>Nova senha<input id="va-r-senha" type="password" placeholder="mínimo 8 caracteres" /></label>
            <div class="va-row"><button class="va-a" type="button" data-reset>Redefinir</button></div>
            <p class="va-msg" id="va-msg-reset"></p>
          </div>
        </div>
        <p class="va-msg" id="va-msg-geral"></p>
      </div>
      <div class="va-foot">Isolamento garantido por <b>RLS</b>: <code>owner_id = auth.uid()</code>, com exceção apenas para administradores. Toda alteração de estado é registrada em <code>vivaz_audit</code>.</div>
    </div>`;
  document.body.appendChild(root);

  root.querySelector('[data-fechar]').addEventListener('click', () => root.classList.remove('on'));
  root.addEventListener('click', (e) => { if (e.target === root) root.classList.remove('on'); });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') root.classList.remove('on');
  });

  let USERS = [];

  function msg(id, texto, tipo) {
    const el = root.querySelector(id);
    if (!el) return;
    el.textContent = texto || '';
    el.className = 'va-msg ' + (tipo || '');
  }

  function options(sel, list) {
    const el = root.querySelector(sel);
    const atual = el.value;
    el.innerHTML = list.map((u) => `<option value="${esc(u.id)}">${esc(u.name)} · ${esc(u.email)}</option>`).join('');
    if (atual && list.some((u) => u.id === atual)) el.value = atual;
  }

  function render(list) {
    USERS = list;
    const soma = (k) => list.reduce((a, u) => a + (u.carteira?.[k] || 0), 0);
    root.querySelector('#va-kpis').innerHTML = [
      [list.length, 'usuários'],
      [list.filter((u) => u.status === 'ativo').length, 'ativos'],
      [soma('properties'), 'imóveis'],
      [soma('contacts'), 'clientes'],
      [soma('deals'), 'negócios'],
    ].map(([v, l]) => `<div class="va-kpi"><b>${n(v)}</b><span>${l}</span></div>`).join('');

    root.querySelector('#va-linhas').innerHTML = list.map((u) => {
      const c = u.carteira || {};
      const ini = (u.name || '?').trim().charAt(0).toUpperCase();
      return `<tr data-id="${esc(u.id)}">
        <td><div class="va-who"><span class="va-av">${esc(ini)}</span>
          <span><b>${esc(u.name)}</b><small>${esc(u.email)}</small></span></div></td>
        <td><select data-role>${['admin', 'gerente', 'corretor'].map((r) =>
          `<option value="${r}"${u.role === r ? ' selected' : ''}>${r === 'admin' ? 'Administrador' : r === 'gerente' ? 'Gerente' : 'Corretor'}</option>`).join('')}</select></td>
        <td><span class="va-pill ${u.status === 'ativo' ? 'on' : 'off'}">${u.status === 'ativo' ? 'Ativo' : 'Inativo'}</span></td>
        <td><span style="font-size:11.5px;color:#6b7280">${n(c.properties || 0)} imóveis · ${n(c.contacts || 0)} clientes · ${n(c.deals || 0)} negócios</span></td>
        <td>
          <button class="va-a" type="button" data-toggle>${u.status === 'ativo' ? 'Desativar' : 'Ativar'}</button>
          <button class="va-a" type="button" data-detalhe>Ver carteira</button>
        </td></tr>`;
    }).join('');

    options('#va-ver-user', list);
    options('#va-r-user', list);
    const me = list.find((u) => u.id === ME.id);
    if (me) {
      root.querySelector('#va-p-nome').value = me.name || '';
      root.querySelector('#va-p-phone').value = me.phone || '';
    }
  }

  async function carregar() {
    try {
      const r = await api('/api/admin/users');
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Falha ao carregar');
      render(d.users || []);
      msg('#va-msg-geral', '', '');
    } catch (e) {
      msg('#va-msg-geral', e.message || 'Erro ao carregar usuários.', 'erro');
    }
  }

  async function patch(id, body) {
    const r = await api('/api/users/' + id, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || 'Falha na operação');
    await carregar();
    return d;
  }

  function abrir() { root.classList.add('on'); carregar(); }

  root.addEventListener('change', async (e) => {
    const tr = e.target.closest('tr[data-id]');
    if (tr && e.target.matches('[data-role]')) {
      try { await patch(tr.dataset.id, { role: e.target.value }); msg('#va-msg-geral', 'Papel atualizado.', 'ok'); }
      catch (err) { msg('#va-msg-geral', err.message, 'erro'); }
    }
  });

  root.addEventListener('click', async (e) => {
    const tr = e.target.closest('tr[data-id]');
    if (!tr) return;
    const id = tr.dataset.id;
    if (e.target.matches('[data-toggle]')) {
      const u = USERS.find((x) => x.id === id);
      try { await patch(id, { status: u.status === 'ativo' ? 'inativo' : 'ativo' }); msg('#va-msg-geral', 'Status atualizado.', 'ok'); }
      catch (err) { msg('#va-msg-geral', err.message, 'erro'); }
    }
    if (e.target.matches('[data-detalhe]')) {
      root.querySelector('#va-ver-user').value = id;
      try {
        const r = await api('/api/admin/state?user_id=' + encodeURIComponent(id));
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || 'Falha');
        const rot = { properties: 'Imóveis', contacts: 'Clientes', deals: 'Negócios', leads: 'Oportunidades', tasks: 'Tarefas', docs: 'Documentos', threads: 'Conversas', members: 'Equipe' };
        root.querySelector('#va-chips').innerHTML = Object.entries(d.resumo || {})
          .filter(([k]) => rot[k]).map(([k, v]) => `<span class="va-chip"><b>${n(v)}</b> ${rot[k]}</span>`).join('') || '<span class="va-chip">Carteira vazia</span>';
      } catch (err) { msg('#va-msg-geral', err.message, 'erro'); }
    }
  });

  root.querySelector('[data-criar]').addEventListener('click', async () => {
    const body = {
      name: root.querySelector('#va-n-nome').value.trim(),
      email: root.querySelector('#va-n-email').value.trim(),
      password: root.querySelector('#va-n-senha').value,
      role: root.querySelector('#va-n-role').value
    };
    if (!body.email || !body.name || body.password.length < 8) {
      msg('#va-msg-novo', 'Preencha nome, e-mail e senha (8+ caracteres).', 'erro'); return;
    }
    try {
      const r = await api('/api/users', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Falha ao criar');
      msg('#va-msg-novo', 'Usuário criado com carteira vazia.', 'ok');
      ['#va-n-nome', '#va-n-email', '#va-n-senha'].forEach((s) => { root.querySelector(s).value = ''; });
      await carregar();
    } catch (err) { msg('#va-msg-novo', err.message, 'erro'); }
  });

  root.querySelector('[data-perfil]').addEventListener('click', async () => {
    try {
      const r = await api('/api/profile', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: root.querySelector('#va-p-nome').value.trim(),
          phone: root.querySelector('#va-p-phone').value.trim()
        })
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Falha');
      msg('#va-msg-perfil', 'Perfil atualizado.', 'ok');
      await carregar();
    } catch (err) { msg('#va-msg-perfil', err.message, 'erro'); }
  });

  root.querySelector('[data-senha]').addEventListener('click', async () => {
    try {
      const r = await api('/api/password', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current: root.querySelector('#va-s-atual').value,
          password: root.querySelector('#va-s-nova').value
        })
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Falha');
      msg('#va-msg-perfil', 'Senha alterada.', 'ok');
      root.querySelector('#va-s-atual').value = '';
      root.querySelector('#va-s-nova').value = '';
    } catch (err) { msg('#va-msg-perfil', err.message, 'erro'); }
  });

  root.querySelector('[data-ver]').addEventListener('click', async () => {
    const id = root.querySelector('#va-ver-user').value;
    try {
      const r = await api('/api/admin/state?user_id=' + encodeURIComponent(id));
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Falha');
      const rot = { properties: 'Imóveis', contacts: 'Clientes', deals: 'Negócios', leads: 'Oportunidades', tasks: 'Tarefas', docs: 'Documentos' };
      root.querySelector('#va-chips').innerHTML = Object.entries(d.resumo || {})
        .filter(([k]) => rot[k]).map(([k, v]) => `<span class="va-chip"><b>${n(v)}</b> ${rot[k]}</span>`).join('') || '<span class="va-chip">Carteira vazia</span>';
    } catch (err) { msg('#va-msg-geral', err.message, 'erro'); }
  });

  root.querySelector('[data-reset]').addEventListener('click', async () => {
    const id = root.querySelector('#va-r-user').value;
    const senha = root.querySelector('#va-r-senha').value;
    if (senha.length < 8) { msg('#va-msg-reset', 'Senha com 8+ caracteres.', 'erro'); return; }
    try {
      const r = await api('/api/users/' + id + '/reset-password', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: senha })
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error || 'Falha');
      msg('#va-msg-reset', 'Senha redefinida.', 'ok');
      root.querySelector('#va-r-senha').value = '';
    } catch (err) { msg('#va-msg-reset', err.message, 'erro'); }
  });
})();
