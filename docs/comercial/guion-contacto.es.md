# Guion de contacto con comercializadoras y grandes consumidores

Para Miguel. Sirve para tener entre 8 y 10 conversaciones de unos 20 minutos con quien compra o vende energía en Colombia. No es un guion de venta: el objetivo de las primeras conversaciones es aprender si el producto le sirve a alguien y qué le falta. Si de ahí sale un piloto o un trabajo, mejor.

Material que usas: la página <https://voltia-xi-five.vercel.app/es/business> (tiene la tabla de precisión), el informe de ejemplo (`/informe-ejemplo-volt-ai.pdf`) y la página de Modelos, donde están el método, la comparación detallada y el historial de aciertos.

## Antes de escribir a nadie

1. **Datos de XM.** Los datos son públicos, pero revisa las condiciones de uso de la API de XM antes de cobrar por algo construido con ellos. Cobrar por el pronóstico y el análisis es distinto de revender los datos. Si tienes duda, consúltalo con alguien que sepa de licencias.
2. **Contactos.** El nombre, el correo o el teléfono de una persona son datos personales aunque sean profesionales y públicos. La Ley 1581 de 2012 y el Decreto 1377 de 2013 piden informar quién los guarda, para qué y cómo pedir que se borren, y contar con la autorización de la persona. Pon una línea en el primer mensaje ("Guardo su nombre y correo solo para esta conversación; si prefiere que los borre, respóndame y lo hago") y bórralos cuando te lo pidan. Escribe de a uno, sin envíos masivos. Confírmalo con un abogado antes de armar una lista grande.
3. **Lenguaje.** Di siempre "apoyo a la decisión". No digas que "recomiendas" comprar, vender ni cubrir. Es lo que dice el sitio y lo que te protege.
4. **Título.** No te presentes como "ingeniero" mientras no tengas el título y la matrícula profesional (Ley 842 de 2003): di "desarrollador de datos e IA". Los mensajes de abajo ya lo dicen así.
5. **Cifras.** Usa solo las de la página Para empresas del día en que hablas: cambian con cada corrida. Los días se cuentan desde el último día con precio completo en los datos públicos de XM, unos tres días antes de que se publique el pronóstico, y conviene decirlo así. Las de hoy, para que las tengas a mano:
   - Demanda a 1 a 30 días: error medio 1,9 %, contra 3,4 % de las dos referencias simples.
   - Precio de bolsa: 10,7 % a 1 a 3 días (referencias: 15,3 % y 29,8 %), 21,2 % a 4 a 7 días (29,2 % y 33,1 %) y 40,0 % a 8 a 14 días (45,3 % y 50,0 %).
   - Pasada una semana, el precio queda a la par con un modelo estadístico simple. Dilo tú primero, no esperes a que lo descubran.

## A quién buscar

| Perfil | Qué decide | Cómo encontrarlo |
| --- | --- | --- |
| Gerente o analista de portafolio y compras de energía en una comercializadora | Cuánto comprar en bolsa y cuánto en contratos, y cuándo | La lista pública de agentes comercializadores de XM; en LinkedIn busca "gestión de energía", "portafolio de energía", "trading de energía" |
| Jefe de energía o de compras en una empresa con consumo grande (industria, cemento, siderurgia, centros comerciales, hospitales) | Contratos con comercializadoras, consumo en horas caras | LinkedIn, con "jefe de energía", "gestión energética", "compras de energía" |
| Consultores del mercado eléctrico | Asesoran a los dos anteriores; abren puertas | LinkedIn y los eventos del sector |

Empieza por los consultores y por las empresas medianas: contestan más y no tienen un equipo de modelado propio.

## Mensaje inicial

**Correo** (asunto: *Pronóstico de precio de bolsa con historial público: ¿le sirve a su equipo?*)

> Hola [nombre],
>
> Soy Miguel Angel, desarrollador de datos e IA. Construí Volt-AI, un sistema que pronostica cada día la demanda y el precio de bolsa de Colombia con su rango de incertidumbre, y que guarda cada pronóstico tal como lo emitió para poder evaluarlo en público. Los datos son de XM.
>
> No le escribo para venderle algo todavía: quiero saber si esto le serviría a quien decide compras en [empresa] y qué le faltaría. ¿Tendría 20 minutos esta semana o la próxima? Le dejo un informe de ejemplo con datos reales y la página donde se ve el historial de aciertos, incluidos los casos en que el modelo no gana: <https://voltia-xi-five.vercel.app/es/business>
>
> Guardo su nombre y correo solo para esta conversación; si prefiere que los borre, respóndame y lo hago.
>
> Gracias,
> Miguel Angel
> miguelangel.14130@gmail.com

**LinkedIn** (solicitud de conexión, hasta 300 caracteres)

> Hola [nombre], construí un pronóstico de demanda y precio de bolsa de Colombia con historial público de aciertos. Me gustaría conocer su opinión sobre si le sirve a un equipo de compras de energía. ¿Le parece una charla de 20 minutos?

## La llamada, minuto a minuto

1. **Apertura (1 minuto).** "Gracias por el tiempo. Quiero entender cómo toman hoy sus decisiones de compra y mostrarle algo que estoy construyendo. No voy a venderle nada hoy."
2. **Entender su caso (8 minutos).** Pregunta, escucha y toma notas. Preguntas:
   - ¿Cómo deciden hoy cuánto cubrir con contratos y cuánto dejar a bolsa?
   - ¿Qué horizonte les importa: la semana, el mes, el trimestre?
   - ¿Qué información usan hoy para el precio y de dónde sale?
   - ¿Qué les ha costado más: un pico de precio, una caída, un error de demanda?
   - ¿Tienen un modelo propio? Si lo tienen, ¿qué le falta?
   - ¿Qué tendría que pasar para confiar en un pronóstico externo?
3. **Demostración (6 minutos).** Enséñale en este orden: la página de Precio (rango y probabilidad de picos), el mapa de embalses y, al final, la página de Modelos con el historial. Cuéntale primero dónde el modelo no gana.
4. **Su opinión (3 minutos).** "¿Qué le sirve de esto? ¿Qué le falta para usarlo en una decisión real?" Anota las palabras exactas.
5. **Cierre (2 minutos).** Pide una sola cosa: "¿Le parece si le envío cada semana durante un mes un informe como el del ejemplo, sin costo, y me cuenta si lo usó?". Si dice que sí, ese es el piloto. Si no, pide el nombre de alguien a quien le pueda servir.

## Objeciones y qué responder

| Dicen | Respondes |
| --- | --- |
| "Ya tenemos modelo propio." | "Perfecto. Entonces Volt-AI sirve como segunda opinión: le muestro dónde coincidimos y dónde no. Y el historial público permite comparar sin confiar en mi palabra." |
| "¿Qué tan preciso es?" | Las cifras de la página de Modelos del día. Subraya que la precisión del precio es buena en los primeros 3 días y a la par de un modelo simple pasada una semana. |
| "El precio sube por decisiones que nadie ve venir." | "Tiene razón: no anticipa racionamientos ni cambios regulatorios, y lo dice el sitio. Lo que sí hace es medir el rango y la probabilidad de picos con lo que se sabe." |
| "¿Cuánto cuesta?" | "Todavía no tengo una tarifa. Depende de qué necesite: un informe semanal, acceso a la API o un pronóstico adaptado a su portafolio. Primero quiero entender su caso." No inventes un precio en la llamada. |
| "¿Por qué confiar en una sola persona?" | "El método y el historial de aciertos son públicos y se pueden revisar, y empezamos con un mes de prueba." Menciona el código solo si antes verificas que el repositorio es público. |
| "XM ya publica pronósticos." | Antes de la llamada, revisa qué pronósticos publica XM hoy y en qué se diferencian de los tuyos (horizonte, rango, historial). No afirmes nada que no hayas comprobado. |

## Qué no decir

- "Le garantizo", "siempre acierta" o cualquier promesa de ahorro.
- Cifras de otro día o de memoria. Abre la página Para empresas y léelas ahí.
- Que el historial es "inalterable". Di que cada pronóstico "se guarda tal como se emitió": el pipeline no reescribe lo guardado, pero eso no es lo mismo que una garantía técnica.
- Que el precio está "liquidado" por XM. En el mercado, liquidación es el proceso de XM, con versiones y revisiones. Di "datos públicos de XM con el precio completo".
- Que "recomiendas" comprar o cubrir.
- Un precio sin haber entendido el caso.

## Después de la llamada

- **El mismo día:** correo de agradecimiento con el informe de ejemplo y, si aceptó el piloto, la fecha del primer informe.
- **A los 3 o 4 días:** si no hubo respuesta, un solo recordatorio breve.
- **A los 10 días:** último mensaje con algo útil (por ejemplo, el pronóstico de la semana) y sin presión. Después, no insistas.

## Registro de conversaciones

Copia esta tabla a una hoja de cálculo. Después de 8 a 10 conversaciones, lo que se repite en "Qué le faltó" es lo que hay que construir.

| Fecha | Persona y empresa | Perfil | Horizonte que le importa | Qué le sirvió | Qué le faltó | Siguiente paso |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |
