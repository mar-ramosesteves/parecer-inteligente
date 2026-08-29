-- LeaderTrack: snapshots executivos agregados por rodada e empresa.
-- RASCUNHO PARA REVISAO: ainda nao foi aplicado no Supabase.
-- Nao altera nem exclui tabelas existentes.

begin;

create table if not exists public.leadertrack_execucoes_organizacionais (
    id bigint generated always as identity primary key,
    chave_analise text not null unique,
    codrodada text not null,
    nivel_contexto text not null,
    contexto jsonb not null default '{}'::jsonb,
    filtros jsonb not null default '{}'::jsonb,
    parametros jsonb not null default '{}'::jsonb,
    status text not null default 'pendente'
        check (status in ('pendente', 'processando', 'concluida', 'erro')),
    versao_regras text not null,
    solicitado_por text,
    iniciado_em timestamptz,
    concluido_em timestamptz,
    erro_resumido text,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

create table if not exists public.leadertrack_pacotes_organizacionais (
    id bigint generated always as identity primary key,
    execucao_id bigint not null
        references public.leadertrack_execucoes_organizacionais(id) on delete restrict,
    chave_analise text not null unique,
    codrodada text not null,
    nivel_contexto text not null
        check (nivel_contexto in ('empresa', 'contexto')),
    empresa_codigo text,
    contexto jsonb not null default '{}'::jsonb,
    filtros jsonb not null default '{}'::jsonb,
    amostra jsonb not null default '{}'::jsonb,
    status text not null default 'concluido'
        check (status in ('concluido', 'amostra_insuficiente')),
    pacote_completo jsonb not null,
    hash_origem text not null,
    versao_regras text not null,
    gerado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

create table if not exists public.leadertrack_cruzamentos_organizacionais (
    id bigint generated always as identity primary key,
    pacote_id bigint not null
        references public.leadertrack_pacotes_organizacionais(id) on delete cascade,
    chave_cruzamento text not null,
    familia text not null
        check (familia in ('arquetipos', 'microambiente', 'saude_emocional', 'participacao')),
    dimensoes text[] not null default '{}',
    valores text[] not null default '{}',
    n_arquetipos integer not null check (n_arquetipos >= 0),
    n_microambiente integer not null check (n_microambiente >= 0),
    dados jsonb not null,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now(),
    unique (pacote_id, chave_cruzamento)
);

create table if not exists public.leadertrack_insights_organizacionais (
    id bigint generated always as identity primary key,
    pacote_id bigint not null
        references public.leadertrack_pacotes_organizacionais(id) on delete cascade,
    chave_insight text not null unique,
    camada text not null
        check (camada in (
            'resumo_executivo', 'arquetipos', 'microambiente',
            'saude_emocional', 'cruzamentos', 'recomendacoes'
        )),
    status text not null default 'pendente'
        check (status in ('pendente', 'processando', 'concluida', 'erro')),
    entrada_hash text not null,
    modelo text,
    conteudo jsonb,
    erro_resumido text,
    gerado_em timestamptz,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

create index if not exists idx_lt_execucoes_rodada_status
    on public.leadertrack_execucoes_organizacionais (codrodada, status, criado_em desc);

create index if not exists idx_lt_pacotes_execucao
    on public.leadertrack_pacotes_organizacionais (execucao_id);

create index if not exists idx_lt_pacotes_rodada_nivel_empresa
    on public.leadertrack_pacotes_organizacionais
    (codrodada, nivel_contexto, empresa_codigo, gerado_em desc);

create index if not exists idx_lt_cruzamentos_pacote_familia
    on public.leadertrack_cruzamentos_organizacionais (pacote_id, familia);

create index if not exists idx_lt_insights_pacote_camada_status
    on public.leadertrack_insights_organizacionais (pacote_id, camada, status);

alter table public.leadertrack_execucoes_organizacionais enable row level security;
alter table public.leadertrack_pacotes_organizacionais enable row level security;
alter table public.leadertrack_cruzamentos_organizacionais enable row level security;
alter table public.leadertrack_insights_organizacionais enable row level security;

-- Nenhum navegador recebe acesso direto. O backend interno usa service_role.
revoke all on table public.leadertrack_execucoes_organizacionais from public, anon, authenticated;
revoke all on table public.leadertrack_pacotes_organizacionais from public, anon, authenticated;
revoke all on table public.leadertrack_cruzamentos_organizacionais from public, anon, authenticated;
revoke all on table public.leadertrack_insights_organizacionais from public, anon, authenticated;

grant select, insert, update, delete on table public.leadertrack_execucoes_organizacionais to service_role;
grant select, insert, update, delete on table public.leadertrack_pacotes_organizacionais to service_role;
grant select, insert, update, delete on table public.leadertrack_cruzamentos_organizacionais to service_role;
grant select, insert, update, delete on table public.leadertrack_insights_organizacionais to service_role;

grant usage, select on sequence public.leadertrack_execucoes_organizacionais_id_seq to service_role;
grant usage, select on sequence public.leadertrack_pacotes_organizacionais_id_seq to service_role;
grant usage, select on sequence public.leadertrack_cruzamentos_organizacionais_id_seq to service_role;
grant usage, select on sequence public.leadertrack_insights_organizacionais_id_seq to service_role;

comment on table public.leadertrack_execucoes_organizacionais is
    'Historico auditavel das geracoes administrativas de snapshots LeaderTrack.';
comment on table public.leadertrack_pacotes_organizacionais is
    'Snapshots agregados por empresa e contexto, sem respostas individuais.';
comment on table public.leadertrack_cruzamentos_organizacionais is
    'Recortes agregados que respeitam a amostra minima configurada.';
comment on table public.leadertrack_insights_organizacionais is
    'Analises e recomendacoes de IA separadas do calculo deterministico.';

commit;

select 'SNAPSHOTS_EXECUTIVOS_LEADERTRACK_CRIADOS' as resultado;
