# Scouting Mundial

Aplicación de scouting de jugadores en vivo, pensada para etiquetar acciones
mientras ves un partido por televisión. Hecha en Python con Streamlit, con
guardado en la nube vía Supabase para que tus sesiones sobrevivan al deploy
y sean accesibles desde cualquier ordenador.

## Funcionalidades

- **Menú de sesiones**: lista de partidos guardados con resumen (marcador,
  número de jugadores y acciones). Abre, borra o crea sesiones nuevas.
- **Panel de 50 acciones** organizado por bloques (construcción, regate,
  movimiento sin balón, finalización, defensa, transiciones, balón parado).
- **Resultados específicos por tipo**: OK/Fallo para pases, Encontrado/No
  encontrado para desmarques, Puerta/Gol/Fuera para remates.
- **Selector rápido de jugador** como chips arriba del panel, con flechas
  para pasar al anterior/siguiente.
- **Zonas del campo** (1er, 2º, 3er tercio) que se aplican a cada acción.
- **Cronómetro de partido** que sella el minuto exacto en cada acción.
- **Atajos de teclado** para ir más rápido.
- **Guardado automático** en Supabase tras cada cambio.
- **Exportación a CSV** con tabla plana (acciones + datos del partido).

## Atajos de teclado

- `Z` — Deshacer última acción
- `Espacio` — Iniciar / pausar cronómetro
- `1` / `2` / `3` — Cambiar zona del campo
- `←` / `→` — Jugador anterior / siguiente

Los atajos se desactivan automáticamente cuando estás escribiendo en un
campo de texto, para no interferir.

## Instalación local

1. Clona o descarga este repositorio.
2. Instala dependencias:
   ```
   pip install -r requirements.txt
   ```
3. Crea un proyecto en [supabase.com](https://supabase.com) y la tabla:
   ```sql
   create table sesiones (
       id uuid primary key default gen_random_uuid(),
       nombre text not null,
       competicion text,
       fecha text,
       equipo_local text,
       equipo_visitante text,
       goles_local int default 0,
       goles_visitante int default 0,
       posesion_local int default 50,
       jugadores jsonb default '[]'::jsonb,
       events jsonb default '[]'::jsonb,
       notas text default '',
       created_at timestamptz default now(),
       updated_at timestamptz default now()
   );
   alter table sesiones disable row level security;
   ```
4. Edita `.streamlit/secrets.toml` con tu URL y anon key:
   ```toml
   SUPABASE_URL = "https://xxxxx.supabase.co"
   SUPABASE_KEY = "eyJ..."
   ```
5. Lanza la app:
   ```
   streamlit run scouting_app.py
   ```

## Deploy en Streamlit Community Cloud

1. Sube el repositorio a GitHub (el `.gitignore` ya excluye `secrets.toml`).
2. En [share.streamlit.io](https://share.streamlit.io), conecta el repo y
   crea la app apuntando a `scouting_app.py`.
3. En **Settings → Secrets** de la app, pega:
   ```toml
   SUPABASE_URL = "https://xxxxx.supabase.co"
   SUPABASE_KEY = "eyJ..."
   ```
4. Listo. La app despliega y tus sesiones de Supabase aparecen al instante.

## Estructura del proyecto

```
scouting_mundial/
├── scouting_app.py          # App principal (UI + flujo)
├── storage.py               # Capa de almacenamiento contra Supabase
├── styles.css               # Tema "Full Fútbol" (césped)
├── requirements.txt
├── README.md
├── .gitignore               # Excluye secrets.toml
└── .streamlit/
    ├── config.toml          # Tema base de Streamlit
    └── secrets.toml         # Credenciales (NO subir al repo)
```

## Notas

- Las sesiones se guardan en una sola tabla `sesiones` de Supabase. Cada fila
  es un partido completo con sus jugadores y acciones como JSON.
- El guardado es automático tras cada acción, cambio de jugador, edición de
  datos del partido o nota.
- Si pierdes la conexión a Supabase, las acciones se siguen registrando en
  memoria; al volver la conexión, el siguiente guardado las sube todas.
