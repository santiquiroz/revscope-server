# revscope-server

Servidor open source y **auto-hosteable** para [RevScope](https://github.com/santiquiroz/revscope) — la suite de telemetría OBD2 para Android.

La app funciona 100% offline sin este servidor. Esto agrega la capa social/colaborativa, y **tú eliges a qué servidor apuntar** desde Ajustes: el público, el de tu grupo de rodada, o el tuyo en una Raspberry.

## Principios de diseño (contrato con la app)

1. **Offline-first, siempre.** La app es completamente funcional sin servidor. Todo lo que este servidor agrega es *aditivo*: si no hay red o el server está caído, la app se comporta exactamente igual que sin servidor configurado.
2. **Fallo silencioso.** Un server inalcanzable jamás produce errores visibles ni bloquea nada — como mucho, un indicador discreto de "sin sincronizar".
3. **Sync oportunista.** Los huecos se suben cuando se puede y se cachean localmente los descargados; la fuente de verdad local nunca depende del server.
4. **El usuario elige su server.** URL configurable en Ajustes; el público es solo un default.

## Features

| Feature | Qué hace |
|---|---|
| 🕳️ **Huecos crowdsourced** | Los golpes que detecta el IMU de cada usuario se comparten por región. Dedupe server-side (30 m): un hueco reportado por 12 motos vale más que uno reportado por una. |
| 🏍️ **Rodadas en grupo** | Sala con código de 6 letras + WebSocket: cada miembro ve la posición de los demás en el mapa en vivo (~1 Hz). |
| 👻 **Fantasmas compartidos** | Sube tu mejor vuelta de una pista (línea de meta) y descarga las de otros para correr contra su fantasma en Modo Pista. |

## Quickstart (self-host)

```bash
git clone https://github.com/santiquiroz/revscope-server
cd revscope-server
cp .env.example .env      # revisa AUTH_MODE
docker compose up -d
# API en http://localhost:8080 — apunta la app ahí desde Ajustes
```

## Autenticación — tres modos

El servidor **no tiene base de usuarios propia**. `AUTH_MODE` en `.env`:

| Modo | Para quién | Cómo |
|---|---|---|
| `none` | Tu LAN / grupo de confianza | Sin auth. Identidad = apodo que manda la app. |
| `token` | Server del parche | Un `AUTH_TOKEN` compartido — igual que una clave de WiFi. |
| `oidc` | Instancia pública / seria | Valida JWT de **cualquier issuer OpenID Connect**: Keycloak, Authentik, Zitadel, Google, o tu propio proveedor. Configura `OIDC_ISSUER` + `OIDC_AUDIENCE`. |

OIDC es la apuesta a futuro: la identidad vive en un proveedor dedicado (con sus buenas prácticas: MFA, recovery, rate limiting) y este servidor solo **valida tokens**. Si mañana cambias de proveedor de identidad, aquí solo cambia una URL.

## API (v0)

```
GET  /healthz                        — estado
POST /v1/potholes                    — reportar hueco {lat, lon, severity_g}
GET  /v1/potholes?bbox=...           — huecos de una región
POST /v1/rooms                       — crear sala de rodada → {code}
WS   /v1/rooms/{code}/ws             — unirse; enviar/recibir posiciones JSON
POST /v1/ghosts                      — subir vuelta {finish_lat, finish_lon, time_ms, points}
GET  /v1/ghosts?near=lat,lon         — vueltas de esa pista (mejores primero)
```

Todos los endpoints (menos `/healthz`) exigen `Authorization: Bearer …` en modos `token`/`oidc`.

## Stack

FastAPI · PostgreSQL + PostGIS · asyncpg · Docker Compose. Sin estado fuera de Postgres salvo las salas en vivo (memoria — una rodada es efímera por diseño).

## Privacidad

- Posiciones en vivo: **solo** se retransmiten a la sala, nunca se persisten.
- Huecos: se guarda ubicación + severidad, **jamás** quién lo reportó ni su recorrido.
- Fantasmas: subir es opt-in explícito por vuelta; el track es público para esa pista.

## Roadmap

- [ ] Rate limiting por identidad
- [ ] Leaderboards por pista
- [ ] Export de huecos a formato OSM (devolverle a la comunidad)
- [ ] Federación entre instancias (¿tu server le comparte huecos al público?)

## Licencia

MIT. La app RevScope es Apache 2.0 — proyectos hermanos, licencias independientes.
