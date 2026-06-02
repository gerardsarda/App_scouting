-- ============================================================================
-- Migración Supabase — columnas necesarias para la app de scouting
-- ============================================================================
-- Ejecuta esto en Supabase → SQL Editor → New query → Run.
-- Son cambios aditivos: no borran datos.
-- ============================================================================

-- 1) Tipo de sesión: separa sesiones de jugadores de las de equipo.
--    Valores: 'jugadores' o 'equipo'. Por defecto 'jugadores'.
ALTER TABLE sesiones
    ADD COLUMN IF NOT EXISTS tipo text NOT NULL DEFAULT 'jugadores';

-- 2) Posiciones de los jugadores de la sesión (mapa nombre -> código de posición,
--    p. ej. {"10 - Messi": "MP"}). Se guarda como JSON.
ALTER TABLE sesiones
    ADD COLUMN IF NOT EXISTS posiciones jsonb NOT NULL DEFAULT '{}'::jsonb;

-- (Opcional) Marcar manualmente una sesión existente como de equipo:
-- UPDATE sesiones SET tipo = 'equipo' WHERE id = 'PEGA-AQUI-EL-ID';
