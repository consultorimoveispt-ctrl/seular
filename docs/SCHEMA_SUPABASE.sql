-- ============================================================================
-- VIVAZ · schema definitivo (multi-tenant INDIVIDUAL) para Supabase/Postgres
-- Projeto: seular · ref ezmvbknqtxupibbhyskp · aplicado em 07/11/2026
--
-- Modelo: CADA USUÁRIO tem sua própria carteira (imóveis, clientes, negócios,
-- leads, tarefas, documentos, conversas, comissões/financeiro). O isolamento é
-- garantido por RLS no banco, não apenas pela aplicação:
--     owner_id = auth.uid()  OR  vivaz_is_admin()
-- O admin é a única exceção e enxerga todas as carteiras pelo painel.
--
-- Ordem de aplicação:
--   1) este arquivo (SQL Editor)
--   2) criar admin@vivaz.local no Supabase Auth
--   3) SEED_SUPABASE.sql  (dados de demonstração SÓ na carteira do admin)
--   4) python3 docs/aplicar_supabase.py  (idempotente; faz 2, 3 e o Storage)
-- ============================================================================

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------- perfis ---
create table if not exists public.vivaz_profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  name          text not null,
  role          text not null default 'corretor'
                check (role in ('admin','gerente','corretor')),
  status        text not null default 'ativo'
                check (status in ('ativo','inativo')),
  phone         text,
  avatar_url    text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  last_login_at timestamptz
);

-- ------------------------------------------------------- estado por dono ---
create table if not exists public.vivaz_state (
  owner_id    uuid not null references auth.users(id) on delete cascade,
  collection  text not null,
  payload     jsonb not null,
  updated_at  timestamptz not null default now(),
  updated_by  uuid references auth.users(id) on delete set null,
  primary key (owner_id, collection)
);
create index if not exists vivaz_state_owner_idx on public.vivaz_state(owner_id);

-- ------------------------------------------------------------ auditoria ---
create table if not exists public.vivaz_audit (
  id          bigint generated always as identity primary key,
  user_id     uuid references auth.users(id) on delete set null,
  owner_id    uuid references auth.users(id) on delete set null,
  action      text not null,
  detail      text,
  created_at  timestamptz not null default now()
);
create index if not exists vivaz_audit_created_idx
  on public.vivaz_audit (created_at desc);

-- ------------------------------------------------------------- helpers ---
create or replace function public.vivaz_is_admin()
returns boolean language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.vivaz_profiles p
                 where p.id = auth.uid() and p.role = 'admin' and p.status = 'ativo');
$$;

-- Carteira vazia, mas COMPATÍVEL com o bundle original: ele faz
-- G.threads[0].id, então é obrigatório haver ao menos uma conversa.
create or replace function public.vivaz_init_state(
  p_user uuid, p_name text, p_email text)
returns integer language plpgsql security definer set search_path = public as $$
declare n integer; v_member text; v_thread jsonb;
begin
  v_member := 'm-' || p_user::text;
  v_thread := jsonb_build_array(jsonb_build_object(
    'id', 'th-' || p_user::text,
    'title', 'Boas-vindas',
    'people', jsonb_build_array(v_member),
    'propertyId', null,
    'unread', 0,
    'pinned', true,
    'msgs', jsonb_build_array(jsonb_build_object(
      'id', 'msg-boas-vindas', 'from', v_member,
      'at', (extract(epoch from now()) * 1000)::bigint,
      'kind', 'text',
      'text', 'Sua carteira está pronta. Cadastre imóveis, clientes e negócios para começar.'
    ))
  ));

  insert into public.vivaz_state(owner_id, collection, payload, updated_by) values
    (p_user,'version',    '1'::jsonb, p_user),
    (p_user,'seededOn',   to_jsonb(to_char(now(),'YYYY-MM-DD')), p_user),
    (p_user,'members',    jsonb_build_array(jsonb_build_object(
       'id',v_member,'name',p_name,'role','Corretor','photo','imani-brooks',
       'target',0,'phone','','email',p_email)), p_user),
    (p_user,'contacts',   '[]'::jsonb, p_user),
    (p_user,'properties', '[]'::jsonb, p_user),
    (p_user,'deals',      '[]'::jsonb, p_user),
    (p_user,'leads',      '[]'::jsonb, p_user),
    (p_user,'tasks',      '[]'::jsonb, p_user),
    (p_user,'docs',       '[]'::jsonb, p_user),
    (p_user,'threads',    v_thread, p_user),
    (p_user,'activity',   '[]'::jsonb, p_user),
    (p_user,'notices',    '[]'::jsonb, p_user),
    (p_user,'settings',   jsonb_build_object(
       'name',p_name,'email',p_email,'role','Corretor','agency','',
       'created',to_char(now(),'YYYY-MM-DD'),
       'notify',jsonb_build_object('leads',false,'offers',false,
                                   'viewings',false,'digest',false)), p_user)
  on conflict (owner_id, collection) do nothing;
  get diagnostics n = row_count;
  insert into public.vivaz_audit(user_id, owner_id, action, detail)
    values (p_user, p_user, 'user:init', n || ' coleções (carteira vazia)');
  return n;
end $$;

create or replace function public.vivaz_handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.vivaz_profiles (id, name, role)
  values (new.id,
          coalesce(new.raw_user_meta_data->>'name', split_part(new.email,'@',1)),
          coalesce(new.raw_user_meta_data->>'role', 'corretor'))
  on conflict (id) do nothing;
  perform public.vivaz_init_state(new.id,
      coalesce(new.raw_user_meta_data->>'name', split_part(new.email,'@',1)),
      new.email);
  return new;
end $$;

drop trigger if exists vivaz_on_auth_user_created on auth.users;
create trigger vivaz_on_auth_user_created
  after insert on auth.users
  for each row execute function public.vivaz_handle_new_user();

-- Impede que um não-admin se auto-promova via PATCH no próprio perfil.
create or replace function public.vivaz_guard_profile()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if not public.vivaz_is_admin() then
    if new.role is distinct from old.role or new.status is distinct from old.status then
      raise exception 'Somente administradores podem alterar papel ou status'
        using errcode = '42501';
    end if;
  end if;
  new.updated_at = now();
  return new;
end $$;
drop trigger if exists vivaz_profile_guard on public.vivaz_profiles;
create trigger vivaz_profile_guard before update on public.vivaz_profiles
  for each row execute function public.vivaz_guard_profile();

-- Sync da UI: substitui ATOMICAMENTE só as coleções do dono.
-- Obs.: o Postgres deste projeto exige WHERE em DELETE (guarda anti-destruição).
create or replace function public.vivaz_replace_state(p_state jsonb, p_user uuid)
returns integer language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  if p_user is distinct from auth.uid() and not public.vivaz_is_admin() then
    raise exception 'Acesso negado: carteira de outro usuário'
      using errcode = '42501';
  end if;
  delete from public.vivaz_state
    where owner_id = p_user and collection is not null;
  insert into public.vivaz_state(owner_id, collection, payload, updated_by)
    select p_user, key, value, auth.uid() from jsonb_each(p_state);
  get diagnostics n = row_count;
  insert into public.vivaz_audit(user_id, owner_id, action, detail)
    values (auth.uid(), p_user, 'state:sync', n || ' coleções');
  return n;
end $$;

-- ------------------------------------------------------------------ RLS ---
alter table public.vivaz_profiles enable row level security;
alter table public.vivaz_state   enable row level security;
alter table public.vivaz_audit   enable row level security;

drop policy if exists vivaz_state_all    on public.vivaz_state;
drop policy if exists vivaz_state_select on public.vivaz_state;
drop policy if exists vivaz_state_insert on public.vivaz_state;
drop policy if exists vivaz_state_update on public.vivaz_state;
drop policy if exists vivaz_state_delete on public.vivaz_state;
create policy vivaz_state_select on public.vivaz_state for select
  using (owner_id = auth.uid() or public.vivaz_is_admin());
create policy vivaz_state_insert on public.vivaz_state for insert
  with check (owner_id = auth.uid() or public.vivaz_is_admin());
create policy vivaz_state_update on public.vivaz_state for update
  using (owner_id = auth.uid() or public.vivaz_is_admin())
  with check (owner_id = auth.uid() or public.vivaz_is_admin());
create policy vivaz_state_delete on public.vivaz_state for delete
  using (owner_id = auth.uid() or public.vivaz_is_admin());

drop policy if exists vivaz_profiles_select on public.vivaz_profiles;
drop policy if exists vivaz_profiles_update on public.vivaz_profiles;
create policy vivaz_profiles_select on public.vivaz_profiles for select
  using (id = auth.uid() or public.vivaz_is_admin());
create policy vivaz_profiles_update on public.vivaz_profiles for update
  using (id = auth.uid() or public.vivaz_is_admin())
  with check (id = auth.uid() or public.vivaz_is_admin());

drop policy if exists vivaz_audit_insert on public.vivaz_audit;
drop policy if exists vivaz_audit_select on public.vivaz_audit;
create policy vivaz_audit_insert on public.vivaz_audit for insert
  with check (user_id = auth.uid() or public.vivaz_is_admin());
create policy vivaz_audit_select on public.vivaz_audit for select
  using (public.vivaz_is_admin() or user_id = auth.uid());

-- ------------------------------- views (security_invoker mantém o RLS) ---
create or replace view public.vivaz_members    with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'members';
create or replace view public.vivaz_contacts   with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'contacts';
create or replace view public.vivaz_properties with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'properties';
create or replace view public.vivaz_deals      with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'deals';
create or replace view public.vivaz_leads      with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'leads';
create or replace view public.vivaz_tasks      with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'tasks';
create or replace view public.vivaz_docs       with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'docs';
create or replace view public.vivaz_threads    with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'threads';
create or replace view public.vivaz_activity   with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'activity';
create or replace view public.vivaz_notices    with (security_invoker = true) as
  select x.item, s.owner_id from public.vivaz_state s cross join lateral jsonb_array_elements(s.payload) x(item) where s.collection = 'notices';

-- ============================================================================
-- FIM DO SCHEMA
-- 'settings', 'version' e 'seededOn' são escalares/objeto e ficam em
-- vivaz_state; as views cobrem apenas as coleções em array.
-- Storage: bucket público 'vivaz-fotos' com 51 imagens (aplicar_supabase.py).
-- ============================================================================
