-- PR-Critical-Mode-LLM-Expansion: Hotline 의 admin 관리 가능 table.
-- Admin panel 에서 hotline message 수정 가능 — 코드 변경 X.

create table if not exists nexus_critical_hotlines (
    kind text not null primary key,
    title text not null,
    message text not null,
    contact text not null,
    updated_at timestamptz not null default now(),
    updated_by text
);

-- 초기 seed
insert into nexus_critical_hotlines (kind, title, message, contact) values
    (
        'safety',
        '🚨 응급 상황',
        '즉시 응급 대응이 필요한 상황입니다. 119 또는 회사 안전팀에 연락하세요.',
        '119 / 회사 안전팀 02-XXX-XXXX'
    ),
    (
        'harassment',
        '📞 신고 안내',
        '이 사안은 신고가 필요한 critical 영역입니다. 익명 신고 가능합니다.',
        '인사교육팀 02-XXX-XXXX / CSR팀 02-XXX-XXXX / 익명 신고 (블라섬 VOE)'
    )
on conflict (kind) do nothing;

-- RLS — anon read, service insert/update
alter table nexus_critical_hotlines enable row level security;

drop policy if exists "anon_select_hotlines" on nexus_critical_hotlines;
create policy "anon_select_hotlines" on nexus_critical_hotlines
    for select using (true);

drop policy if exists "service_all_hotlines" on nexus_critical_hotlines;
create policy "service_all_hotlines" on nexus_critical_hotlines
    for all using (auth.role() = 'service_role');

-- 권한
grant select on nexus_critical_hotlines to anon;
grant all on nexus_critical_hotlines to service_role;
