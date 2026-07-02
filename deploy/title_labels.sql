-- Cache for the LLM title classifier (engine/title_classifier.py). Each distinct
-- normalized title is classified once (software: yes/no) and reused across runs,
-- so the model is called only for titles never seen before. Run once in the
-- Supabase SQL editor. RLS disabled to match the rest of the project.
create table if not exists public.title_labels (
  title_norm   text primary key,          -- lowercased, whitespace-collapsed title
  is_software  boolean not null,
  model        text,                       -- model slug that produced the label
  created_at   timestamptz default now()
);

alter table public.title_labels disable row level security;
