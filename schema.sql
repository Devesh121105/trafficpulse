begin;

create table if not exists public.road_segments (
    id text primary key,
    label text not null,
    latitude double precision not null,
    longitude double precision not null
);

alter table public.road_segments
    add column if not exists active boolean not null default true;

-- Keep old road IDs and their foreign-key-linked readings and forecasts.
update public.road_segments
set active = false
where id in ('ito', 'aiims', 'dhaula', 'pitampura');

insert into public.road_segments (id, label, latitude, longitude, active)
values
    ('rohini-5', 'Rohini Sector 5', 28.711948, 77.107817, true),
    ('madhuban-chowk', 'Madhuban Chowk (Outer Ring Road)', 28.70560067, 77.13226299, true),
    ('rohini-7', 'Rohini Sector 7', 28.709386, 77.112108, true),
    ('rithala', 'Rithala', 28.7209, 77.1073, true),
    ('prashant-vihar', 'Prashant Vihar', 28.71079, 77.13414, true),
    ('rohini-16', 'Rohini Sector 16', 28.739163, 77.127274, true)
on conflict (id) do update set
    label = excluded.label,
    active = true;

create table if not exists public.traffic_readings (
    road_id text references public.road_segments(id),
    collected_at timestamptz,
    current_speed real not null check (current_speed >= 0),
    free_flow_speed real check (free_flow_speed > 0),
    primary key (road_id, collected_at)
);

create table if not exists public.traffic_forecasts (
    road_id text references public.road_segments(id),
    issued_at timestamptz,
    target_at timestamptz not null,
    model text not null,
    predicted_speed real not null check (predicted_speed >= 0),
    primary key (road_id, issued_at)
);

alter table public.road_segments enable row level security;
alter table public.traffic_readings enable row level security;
alter table public.traffic_forecasts enable row level security;

commit;
