# Presencia pública: LinkedIn, CV y publicación

Para Miguel. Textos listos para pegar, en español e inglés. Complementan el [guion de contacto](guion-contacto.es.md), que cubre los mensajes directos y la llamada.

**Antes de publicar, revisa las cifras.** Cambian con cada corrida de entrenamiento. Ábrelas en <https://voltia-xi-five.vercel.app/es/business> el día que publiques; las de abajo son las del 26 de octubre de 2026 (50 fechas pasadas de prueba).

| Medida | Modelo | Referencia simple | ETS |
| --- | --- | --- | --- |
| Demanda, error medio (MAPE) | 1,9 % | 3,4 % | 3,4 % |
| Precio, 1 a 3 días | 10,7 % | 29,8 % | 15,3 % |
| Precio, 4 a 7 días | 21,2 % | 33,1 % | 29,2 % |
| Precio, 8 a 14 días | 40,0 % | 50,0 % | 45,3 % |

Lo que **no** debes decir: que el historial en vivo "demuestra" algo (todavía es corto), que el precio gana en todos los horizontes (pasada una semana queda a la par con ETS), que recomiendas comprar o vender, ni que eres ingeniero (di "desarrollador de datos e IA").

## Titular de LinkedIn

- ES: `Desarrollador de datos e IA · Pronóstico de demanda y precio de bolsa de energía en Colombia · Volt-AI`
- EN: `Data & AI developer · Colombian power-market demand and spot-price forecasting · Volt-AI`

## Sección "Acerca de"

**ES**

> Construyo sistemas que convierten datos públicos en decisiones. Mi proyecto más reciente es Volt-AI: pronostica cada día la demanda de electricidad de Colombia (30 días) y el precio de bolsa (14 días) con su rango de incertidumbre, y guarda cada pronóstico tal como lo emitió para evaluarlo en público.
>
> En 50 fechas pasadas que el modelo no había visto, el error medio de la demanda es 1,9 %, frente a 3,4 % de una referencia simple. El precio supera a las dos referencias en los primeros días; pasada una semana queda a la par con un método estadístico sólido, y el sitio lo dice así.
>
> Python (pipeline diario, LightGBM, backtesting), PostgreSQL, Next.js, y un analista de IA que responde solo con consultas validadas.
>
> Si compras o vendes energía en Colombia y quieres ver si encaja en tu caso: miguelangel.14130@gmail.com

**EN**

> I build systems that turn public data into decisions. My latest project is Volt-AI: every day it forecasts Colombian electricity demand (30 days) and the spot price (14 days) with an uncertainty range, and stores each forecast as first issued so it can be scored in public.
>
> Over 50 past dates the model had not seen, demand error averages 1.9 % against 3.4 % for a simple reference. The price beats both references in the first days and stays level with a strong statistical method beyond a week, and the site says so.
>
> Python (daily pipeline, LightGBM, backtesting), PostgreSQL, Next.js and an AI analyst that answers only through validated lookups.
>
> If you buy or sell energy in Colombia and want to see whether it fits your case: miguelangel.14130@gmail.com

## Proyecto en "Experiencia" o "Proyectos" (viñetas para el CV)

**ES**

- Diseñé y operé un pipeline diario (Python, GitHub Actions, PostgreSQL) que descarga datos públicos de XM, los valida, entrena modelos y publica pronósticos de demanda y precio con intervalos calibrados.
- Evalué con backtesting en 50 fechas fijas del calendario frente a dos referencias: error medio de demanda de 1,9 % contra 3,4 %, e intervalos del 80 % con cobertura medida cercana a 0,8.
- Reuní la evidencia de lo que no funcionó (50 candidatos de precio, entre ellos ensambles, redes y modelos de series de tiempo) y la publiqué en la ficha del modelo.
- Publiqué el sitio (Next.js, español e inglés) con una API REST, rol de base de datos de solo lectura, CSP estricta, CodeQL y respaldo semanal de los datos que no se pueden recuperar.
- Construí un analista de IA limitado a herramientas tipadas que nunca ejecuta SQL libre.

**EN**

- Designed and ran a daily pipeline (Python, GitHub Actions, PostgreSQL) that fetches XM public data, validates it, trains models and publishes demand and price forecasts with calibrated intervals.
- Evaluated with backtesting on 50 fixed calendar dates against two references: demand error 1.9 % against 3.4 %, and 80 % intervals with measured coverage close to 0.8.
- Documented what did not work (50 price candidates, including ensembles, neural nets and time-series models) in the public model card.
- Shipped the site (Next.js, Spanish and English) with a REST API, a read-only database role, strict CSP, CodeQL and a weekly backup of the data that cannot be refetched.
- Built an AI analyst limited to typed tools that never runs free-form SQL.

## Publicación (ES)

> Construí un sistema que pronostica la demanda y el precio de bolsa de la electricidad en Colombia, y lo mide en público.
>
> Cada día, Volt-AI guarda su pronóstico antes de que XM publique el resultado, y después lo compara con lo que pasó, con aciertos y errores a la vista.
>
> Lo que midió en 50 fechas pasadas que no había visto:
> • Demanda: error medio de 1,9 % (la referencia simple: 3,4 %)
> • Precio a 1-3 días: 10,7 % (ETS: 15,3 %; referencia simple: 29,8 %)
> • Pasada una semana, el precio queda a la par con ETS. Por eso el sitio lo muestra como un rango, no como un número exacto.
>
> Probé 50 variantes para bajar el error del precio. La mayoría no ayudó, y eso también está documentado.
>
> Si compras o vendes energía en Colombia, la página para empresas tiene la precisión medida y un informe de ejemplo: https://voltia-xi-five.vercel.app/es/business
>
> Código y método: https://github.com/Cabranchis/volt-ai
>
> #Energía #Colombia #CienciaDeDatos #MercadoEléctrico

## Publicación (EN)

> I built a system that forecasts Colombian electricity demand and spot price, and scores itself in public.
>
> Every day Volt-AI stores its forecast before XM publishes the outcome, then compares it with what happened, hits and misses included.
>
> Measured on 50 past dates it had not seen:
> • Demand: 1.9 % mean error (simple reference: 3.4 %)
> • Price, 1-3 days: 10.7 % (ETS: 15.3 %; simple reference: 29.8 %)
> • Beyond a week the price is level with ETS, so the site shows it as a range, not a point.
>
> I tried 50 variants to lower the price error. Most did not help, and that is documented too.
>
> If you buy or sell energy in Colombia, the business page has the measured accuracy and a sample report: https://voltia-xi-five.vercel.app/en/business
>
> Code and method: https://github.com/Cabranchis/volt-ai
>
> #Energy #Colombia #DataScience #PowerMarkets

## Mensaje directo en inglés (para contactos internacionales)

> Subject: Colombian spot-price forecasts with a public track record
>
> Hi <name>,
>
> I'm Miguel Angel, a data and AI developer. I built Volt-AI, a system that forecasts Colombia's electricity demand and spot price every day with an uncertainty range, and stores each forecast as first issued so it can be scored in public. The data come from XM.
>
> Over 50 past dates it had not seen, demand error averages 1.9 % against 3.4 % for a simple reference, and the price beats both references in the first days (it is level with ETS beyond a week).
>
> Would you have 20 minutes to tell me how your team decides on purchases and contracts, and whether a forecast like this would help? Sample report and measured accuracy: https://voltia-xi-five.vercel.app/en/business (the sample report is in Spanish).
>
> I keep your name and email only for this conversation; reply and I will delete them if you prefer.
>
> Thanks,
> Miguel Angel
> miguelangel.14130@gmail.com

## Orden sugerido para la primera semana

1. Día 1: titular y "Acerca de" en LinkedIn, viñetas en el CV, comprobar que el enlace del repo es `Cabranchis/volt-ai`.
2. Día 2: la publicación (ES o EN, según tu público), a media mañana entre semana.
3. Días 3 a 7: de 1 a 2 mensajes directos al día con el [guion](guion-contacto.es.md), anotando cada conversación en su registro.
4. Antes de la primera llamada: abre la página de Modelos y revisa las cifras del día.
