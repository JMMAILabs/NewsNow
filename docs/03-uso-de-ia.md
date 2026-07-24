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

## Resumen honesto

La IA me ha permitido entregar una solución **más completa y en menos tiempo**:
infraestructura como código, backend, prototipo de IA funcional y documentación. El
valor añadido de mi trabajo está en las **decisiones de arquitectura, la coherencia
del conjunto, la adecuación al enunciado y la verificación de que todo funciona**.
