# VoltIA

**Inteligencia energética para Colombia.** VoltIA ingiere los datos públicos del mercado eléctrico nacional (XM), pronostica la demanda y el precio de bolsa con bandas de incertidumbre, detecta anomalías, explica qué mueve cada pronóstico y ofrece un analista con IA que responde preguntas con datos reales.

[English](README.md) · [Requisitos](docs/requirements.md) · [Arquitectura](docs/architecture.md) · [Decisiones](docs/adr)

> **Estado:** en desarrollo. Fase 1 de 7 (andamiaje y diseño). Este README se completa con capturas, métricas y el enlace a la demo en la fase final.

## Qué hace

- **Pronostica** la demanda diaria a 30 días y el precio de bolsa a 14 días, con bandas P10/P50/P90.
- **Evalúa con honestidad** mediante backtesting de origen rodante frente a baselines (estacional ingenuo y ETS) y publica los resultados aunque sean modestos.
- **Explica** cada pronóstico con los factores SHAP en lenguaje claro.
- **Vigila la hidrología y El Niño**: nivel de embalses, aportes y el índice ONI, que en 2026 está en +2,2.
- **Detecta anomalías** como el confinamiento de 2020 y los años de El Niño.
- **Responde preguntas** con un analista de IA limitado a herramientas tipadas y validadas. Nunca ejecuta SQL libre.
- **Expone una API REST** con especificación OpenAPI.
- **Funciona en español y en inglés.**

## Tecnología

| Capa | Tecnología |
| --- | --- |
| Pipeline | Python 3.12, uv, pandas, pandera, LightGBM, statsmodels, SHAP, SQLAlchemy |
| Base de datos | PostgreSQL (plan gratuito de Neon o Supabase) |
| Web | Next.js, TypeScript, Tailwind CSS, Apache ECharts, next-intl |
| IA | Gemini Flash con el AI SDK de Vercel (opcional) |
| Entrega | GitHub Actions (pipeline diario y CI) y Vercel |

Todo corre en planes gratuitos.

## Estructura del repositorio

```
pipeline/   Paquete Python: fuentes, validación, features, modelos, CLI
web/        Aplicación Next.js y API REST
db/         Migraciones SQL versionadas
docs/       Requisitos, arquitectura, ADRs, ficha del modelo, guía de despliegue
```

## Licencia

MIT. Ver [LICENSE](LICENSE).
