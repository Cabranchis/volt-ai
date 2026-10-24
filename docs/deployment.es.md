# Guía de despliegue

Todo corre en planes gratuitos. Cuatro pasos dependen de ti porque usan tus cuentas y tus secretos: crear la base de datos, crear el repositorio, guardar los secretos y conectar Vercel. La versión en inglés está en [deployment.md](deployment.md).

| Servicio | Para qué | Costo | Notas |
| --- | --- | --- | --- |
| GitHub (repositorio público) | Código, CI y el pipeline diario | Gratis | Actions es gratis en repositorios públicos |
| Neon o Supabase | PostgreSQL | Plan gratuito | La app necesita unos 10 a 20 MB |
| Vercel (Hobby) | La aplicación web | Gratis para proyectos personales | Inicia sesión con tu cuenta de GitHub |
| Google AI Studio | Clave de Gemini para el analista | Plan gratuito | Opcional: sin ella el analista responde con resúmenes fijos |

Los límites de cada proveedor cambian, así que revisa los vigentes antes de depender de ellos. Lo que usa VoltIA, medido con los datos reales en octubre de 2026:

- **Tamaño de la base**: toda la historia desde 2018 (54 789 filas diarias y 4 224 horarias) ocupa 5,6 MB en SQLite. En PostgreSQL súmale los índices: calcula de 15 a 25 MB. El objetivo de diseño es menos de 500 MB.
- **Tiempo del pipeline**: la actualización diaria dura cerca de un minuto. El primer backfill tarda unos 10 minutos, sobre todo por las descargas de generación por planta.
- **Consultas al chat**: máximo 12 preguntas por visitante cada 10 minutos y 400 al día en total (`CHAT_DAILY_LIMIT`); pasado ese tope, el analista responde sin el modelo.

## 1. Crear la base de datos

**Neon**

1. Crea un proyecto llamado `voltia` en la región más cercana a la de Vercel.
2. Copia la cadena de conexión **pooled** (el host contiene `-pooler`). Es tu `DATABASE_URL`, la que usa el pipeline.

**Supabase**

1. Crea un proyecto llamado `voltia`.
2. Copia la cadena del **transaction pooler** (puerto 6543) y reemplaza `[YOUR-PASSWORD]`. Es tu `DATABASE_URL`.

Se aceptan URLs `postgres://` y `postgresql://`; el pipeline las ajusta para el driver `psycopg`.

## 2. Cargar el esquema y la historia (desde tu computador)

```bash
cd pipeline
cp ../.env.example .env        # y edita DATABASE_URL
uv sync
uv run voltia migrate          # crea las tablas y el rol voltia_ro
uv run voltia backfill         # unos 10 minutos, desde 2018-01-01
uv run voltia train --predict  # backtest, modelos finales y pronósticos
uv run voltia anomalies
uv run voltia status           # todos los conjuntos deben decir status=ok
```

`.env` está ignorado por git. Nunca lo subas.

## 3. Darle a la web un rol de solo lectura

La migración crea el rol `voltia_ro` sin contraseña y sin permiso de inicio de sesión. En el editor SQL del proveedor ejecuta:

```sql
ALTER ROLE voltia_ro WITH LOGIN PASSWORD '<una contraseña larga y aleatoria>';
```

Arma una segunda cadena de conexión con ese rol: es `DATABASE_URL_READONLY`. El rol puede leer todas las tablas y escribir solo en `rate_limits` (el limitador del chat). Para comprobarlo, conéctate con él y ejecuta `INSERT INTO series_daily VALUES ('x', '2026-01-01', 1)`: debe fallar con un error de permisos.

## 4. Crear el repositorio y guardar los secretos

```bash
gh repo create voltia --public --source . --remote origin --push
gh secret set DATABASE_URL            # pega la cadena de conexión del pipeline
gh secret set GOOGLE_GENERATIVE_AI_API_KEY   # opcional
```

## 5. Desplegar en Vercel

1. En Vercel elige **Add New, Project** e importa el repositorio `voltia`.
2. Pon **Root Directory** en `web`. Vercel detecta Next.js. En Settings, General, elige **Node.js 22.x**.
3. Agrega estas variables de entorno (Production y Preview, salvo que se indique otra cosa):

| Variable | Valor | Obligatoria |
| --- | --- | --- |
| `DATABASE_URL_READONLY` | la cadena de solo lectura del paso 3 | Production |
| `GOOGLE_GENERATIVE_AI_API_KEY` | clave de Google AI Studio | No |
| `GEMINI_MODEL` | por defecto `gemini-flash-latest` | No |
| `NEXT_PUBLIC_SITE_URL` | tu URL de producción, p. ej. `https://voltia.vercel.app` | Sí |
| `NEXT_PUBLIC_REPO_URL` | `https://github.com/<tu-usuario>/voltia` | No (si está vacía se oculta el enlace) |
| `RATE_LIMIT_SALT` | una cadena aleatoria | Recomendada |
| `CHAT_DAILY_LIMIT` | `400` | No |

No pongas `DATABASE_URL_READONLY` en **Preview**: así las vistas previas de los pull requests usan la instantánea guardada y nunca tocan la base.

4. Despliega. La compilación lee la base mientras prerenderiza, así que la base debe estar accesible en ese momento.

## 6. Comprobar que funciona

- `https://<tu-sitio>/api/v1/health` devuelve `"source": "postgres"` y un `lastDay` reciente en cada serie.
- La barra lateral dice **Base de datos en vivo**, no **Instantánea de demostración**.
- En GitHub, **Actions, Daily pipeline, Run workflow** termina en verde.
- El analista responde una pregunta. Con clave de Gemini muestra las consultas que hizo; sin ella, muestra el aviso de que el modelo no está configurado.

## 7. Actualización de los datos

El workflow del pipeline corre todos los días a las 06:30 hora de Colombia. Las páginas se revalidan cada hora, así que un pronóstico nuevo aparece en cerca de una hora.

## Solución de problemas

| Síntoma | Causa y arreglo |
| --- | --- |
| La compilación falla por la conexión | `DATABASE_URL_READONLY` es incorrecta o el rol no puede iniciar sesión. Repite el paso 3. |
| La compilación falla con `permission denied` | El rol se creó antes que las tablas. Ejecuta `GRANT SELECT ON ALL TABLES IN SCHEMA public TO voltia_ro;`. |
| En producción dice **Instantánea de demostración** | `DATABASE_URL_READONLY` no está definida en el entorno Production. |
| El pipeline falla con errores de `prepared statement` | Usaste la conexión directa con un pooler delante, o al revés. Usa la cadena pooled. |
| El analista nunca usa el modelo | Falta la clave o se agotó su cuota diaria. El aviso aparece en el chat. |
