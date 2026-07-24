# Cómo he utilizado la IA en esta prueba

El enunciado pide explicar en detalle el uso de IA durante la resolución. Lo he
hecho de forma transparente: he usado un **asistente de IA (Claude, vía Claude
Code)** como *pair programmer*, manteniendo yo la dirección técnica, las decisiones
de arquitectura y la validación de todo lo entregado.

---

## Para qué he usado la IA

| Fase | Uso de la IA | Qué he aportado / controlado yo |
|---|---|---|
| **Diseño de arquitectura** | Contrastar opciones AWS (Lambda vs Fargate, DynamoDB vs Aurora, event-driven vs síncrono) y sus trade-offs | La decisión final, adecuándola a "máximo PaaS" y a los picos de tráfico del enunciado |
| **Diagramas** | Generar el código Mermaid de los diagramas | Revisar que el flujo represente la solución real |
| **Terraform** | Redactar los `.tf` y recordar atributos/IDs (p. ej. la managed cache policy de CloudFront, formato del filtro de Streams) | Estructura por dominios, revisión de coherencia entre recursos y del alcance (redes abiertas) |
| **Código Python** | Generar el esqueleto del backend CRUD y de las Lambdas de IA | Diseño del modelo de datos single-table, el fallback mock y el enfoque map-reduce |
| **Documentación** | Redactar y ordenar los documentos explicativos | Contenido técnico, razonamiento y verificación |
| **Verificación** | — | **He ejecutado el prototipo** (`python prototype.py`), **validado la sintaxis del Terraform** (`terraform validate`) y **probado el prompt con un modelo Claude real** sobre Bedrock (PartyRock) |

---

## Principios que he seguido

1. **La IA acelera, no decide.** Cada decisión de arquitectura tiene un razonamiento
   explícito (documentado en `01-infraestructura.md` y `02-desarrollo-ia.md`). La IA
   me ayudó a enumerar alternativas; la elección y su justificación son mías.

2. **Todo lo entregado está revisado.** He leído cada fichero Terraform y cada
   función Python. Corregí, por ejemplo, un problema de *encoding* en Windows
   (cp1252 vs UTF-8) que rompía la ejecución del prototipo con emojis.

3. **Verificación real, no confianza ciega.** El prototipo de IA **se ejecuta** y su
   salida está incluida en la documentación. Instalé Terraform y **`terraform validate`
   pasa correctamente** (*Success! The configuration is valid.*), con el código además
   formateado por `terraform fmt`. Y el prompt del asistente se ha **validado con un
   modelo Claude real sobre Bedrock** (vía PartyRock), no solo con el mock.

4. **Coherencia con el propio caso práctico.** Resulta natural: la prueba trata de
   construir un asistente de IA, y yo mismo he usado IA para construirlo, aplicando
   las mismas ideas (prompts claros, salida estructurada, revisión humana).

---

## La IA dentro del propio producto

Además de usarla como herramienta de desarrollo, la IA es **parte del producto
entregado**: el asistente de resúmenes usa **Amazon Bedrock (Claude)**. Las buenas
prácticas que aplico en el producto son las mismas que he cuidado al trabajar con IA
en esta prueba:

- *Prompts* con rol y formato de salida bien definidos.
- Salida **estructurada (JSON)** y parseo defensivo.
- **Temperatura baja** para fidelidad.
- **Supervisión humana** del resultado.
- Estrategias de **coste/latencia** (modelo adecuado, map-reduce, caching, batch).

---

## Bitácora del desarrollo (qué hicimos y cómo lo verificamos)

Registro cronológico del trabajo, en clave "ingeniero que usa IA como herramienta":
cada fase indica qué se generó con IA, qué se **verificó** y qué se **corrigió** a mano.

1. **Construcción inicial.** Estructura del repo, Terraform por dominios, backend REST
   en Python, prototipo de IA (resumen individual + diario) y documentación. Las
   decisiones de arquitectura las tomo y justifico yo; la IA acelera la redacción.

2. **Primera ejecución y correcciones.** Ejecuté `python prototype.py` → falló por el
   *encoding* de la consola de Windows (cp1252 con emojis); corregido reconfigurando
   `stdout` a UTF-8. Además, el *mock* cortaba los resúmenes a media palabra → añadí
   `_truncar_frases()` para cortar por frase completa.

3. **Terraform real.** Instalé Terraform (winget), `terraform validate` → **Success** y
   `terraform fmt`. Confirmado que valida **sin credenciales AWS**.

4. **Modelo y dudas técnicas.** Modelo por defecto **Claude Haiku 4.5** y verificado que
   `anthropic_version: "bedrock-2023-05-31"` **no es una fecha a actualizar**, sino la
   constante fija de la Messages API en Bedrock (anotado en el código).

5. **Validación con modelo real (coste 0).** Monté en **PartyRock** las dos apps
   (resumen individual y boletín diario *map-reduce*) con Claude a temperatura 0; salida
   JSON limpia y fiel. Capturas en `docs/assets/`.

6. **Acabado "human-in-the-loop" del código.** Quité los banners decorativos idénticos y
   los docstrings uniformes propios de la IA, varié la densidad de comentarios y añadí
   notas pragmáticas reales (`TODO` de paginación, nota `N+1 → BatchGetItem`). De paso
   corregí un comentario que no casaba con el código.

7. **Calidad y automatización.** **Tests** (pytest: idempotencia, batch, parseo JSON),
   **CI** (GitHub Actions: ruff + pytest + terraform validate + tflint), `pyproject.toml`
   y `Makefile`. Todo en verde en local.

8. **Quick wins de infraestructura** (revalidados con `terraform validate` / `tflint`):
   `ReportBatchItemFailures` (fallos parciales de batch), Lambdas en **ARM64**, retención
   de logs, quitado el permiso `dynamodb:Scan` no usado, S3 con *public-access-block* +
   cifrado, y DLQ/retry en el Scheduler diario.

9. **Publicación y CI.** Subí el repo a GitHub; el CI salió verde. Corregí los avisos de
   deprecación de Node 20 subiendo las *actions* a su última versión y añadí reporte
   JUnit descargable + *badge*.

10. **Prueba de carga.** Script **k6** (perfil "pico de influencer") con *smoke* local
    contra un mock (p95 8 ms, 0 errores). El mock monohilo se saturaba bajo carga —justo
    la tesis del ejercicio: un servidor plano no escala; por eso serverless.

11. **Frontend.** Dos SPAs React (Vite): web pública + panel admin, con *fallback mock*.
    `npm run build` verificado; **corregí una vulnerabilidad** del dev server de esbuild
    subiendo a **Vite 8**; añadí un job de frontend al CI.

12. **Afinado de prompts.** Reforcé la **fidelidad** (no inventar; omitir dato ausente),
    la neutralidad y el **JSON estricto** (sin markdown), con ejemplo de formato. Añadí
    *tests de contrato del prompt* que fallan si se borran esas instrucciones.

13. **Diagramas draw.io.** Convertí los diagramas Mermaid al formato **draw.io** que
    sugiere el enunciado (`docs/diagrams/newsnow-arquitectura.drawio`).

> **Mi aportación** en todo esto: las decisiones, el criterio de qué es testeable y qué
> no (escalabilidad = prueba de carga real, no *unit tests*), atrapar los desajustes
> (encoding, comentario erróneo, permiso de más, vulnerabilidad) y **ejecutar y verificar**
> cada cambio en lugar de confiar a ciegas.

---

## Resumen honesto

La IA me ha permitido entregar una solución **más completa y en menos tiempo**:
infraestructura como código, backend, prototipo de IA funcional y documentación. El
valor añadido de mi trabajo está en las **decisiones de arquitectura, la coherencia
del conjunto, la adecuación al enunciado y la verificación de que todo funciona**.
