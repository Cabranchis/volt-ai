# Security policy / Política de seguridad

## Reporting a vulnerability

Please do not open a public issue for a security problem.

- Use GitHub's private reporting: **Security → Report a vulnerability** on this repository.
- Or write to miguelangel.14130@gmail.com with what you found, how to reproduce it and the page or endpoint involved.

I reply within 5 days. Volt-AI is a small project run by one person, so there is no bounty, but I credit reports that lead to a fix if you want to be named.

What is in scope: the website (https://voltia-xi-five.vercel.app), the REST API under `/api/v1`, the chat endpoint and the code in this repository, including the GitHub Actions workflows.
Out of scope: denial-of-service by volume, social engineering, and the services Volt-AI depends on (Vercel, Neon, GitHub, Google, XM).

## Reportar una vulnerabilidad

Por favor no abras un issue público por un problema de seguridad.

- Usa el reporte privado de GitHub: **Security → Report a vulnerability** en este repositorio.
- O escribe a miguelangel.14130@gmail.com con lo que encontraste, cómo reproducirlo y la página o el endpoint.

Respondo en 5 días. Volt-AI es un proyecto pequeño de una sola persona, así que no hay recompensa, pero si quieres, te menciono cuando un reporte lleve a una corrección.

Dentro del alcance: el sitio web, la API REST en `/api/v1`, el endpoint del chat y el código de este repositorio, incluidos los workflows de GitHub Actions.
Fuera del alcance: denegación de servicio por volumen, ingeniería social y los servicios de los que depende Volt-AI (Vercel, Neon, GitHub, Google, XM).

The threat model and the controls in place are described in [docs/security.md](docs/security.md).
