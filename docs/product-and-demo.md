# Producto y demo — HackSpain X-Ray · Embat

> **Estado 19-09-2026: existe la capa de producto (`src/xray/product/`, artefactos en `data/processed/product/`) y una API FastAPI de solo lectura en `backend/` (ver `brief-backend-api.md`, `roadmap-tecnico-mvp.md` y `decisiones.md` §16). No hay frontend ni despliegue público todavía.** Las URLs y métricas de abajo son ejemplos de diseño, no servicios ni resultados comprobados. La implementación actual y siguientes pasos están en [decisiones.md](./decisiones.md). Comprador prioritario: Embat sobre su cartera, o un financiador. Dos caras: deterioro y mejora; la vista del tesorero es complementaria. No hay red de contagio ni promesa de anticipación demostrada.

Documentación de diseño del futuro producto encima del score, la API, el frontend desplegable y el pitch para el jurado.

## Producto: Embat Pulse

**Agente de salud financiera y alertas tempranas** para pymes que ya usan Embat como agregador de tesorería.

### Propuesta de valor

| Para quién | Problema | Solución Pulse |
|---|---|---|
| CFO / tesorero de pyme | Solo ve fotos fijas (balance, rating anual) | Score dinámico mes a mes con trayectoria |
| Mismo usuario | No sabe por qué empeora la caja hasta que es tarde | Alertas 2–3 meses antes + explicación |
| Holding multi-filial | Comparar salud entre filiales es manual | Vista grupo con ranking interno |

### Comprador

**Embat** — la empresa que entrega los datos del reto.

- Ya agregan bancos, ERP y deuda; Pulse es el **tier premium** que monetiza esos datos.
- Modelo: suscripción add-on o upsell en plan Business.
- Pitch: *"Sabéis antes que vuestro banco si algo se tuerce, con datos que ya tenéis conectados."*

No hace falta un plan de negocio completo; sí una respuesta clara a **quién paga y por qué**.

---

## Módulos del producto

| Módulo | Descripción | Datos |
|---|---|---|
| **Health Dashboard** | Lista de empresas ordenada por score, filtros por alerta/trayectoria | `scores.parquet` |
| **Company Detail** | Timeline 24m, descomposición, drivers | `scores` + `explanations.json` |
| **Monitor** | Feed de alertas proactivas | `alerts.json` |
| **Recommendations** | Acciones sugeridas por tipo de alerta | Reglas en alertas |
| **Qué mueve tu nivel** (ficha) | Sensibilidad por empresa: palanca top por 1 % y por 10.000, hasta dónde vale, cuánto para cambiar de tramo, papel en el plan de grupo | `advisor/company_sensitivity/{id}.json` + `.md` (implementado, [group-optimization.md](./group-optimization.md) §6) |
| **Group View** | Plan mecánico intragrupo (D1/P) con evidencia, restricciones activas, alternativas rechazadas y supuestos en pantalla; solo si ≥2 filiales puntuadas | `advisor/group_plans/{group_id}.json` + `.md` (implementado, [group-optimization.md](./group-optimization.md) §5) |

---

## Arquitectura técnica

```
data/processed/
  company_monthly_scores.parquet
  company_explanations.json
  alerts.json
        │
        ▼
   backend/ (FastAPI)
        │
        ▼
   frontend/ (Next.js)
        │
        ▼
   Vercel + Railway/Render (URL pública)
```

### Stack recomendado

| Capa | Tecnología | Motivo |
|---|---|---|
| Backend | FastAPI + Python | Mismo ecosistema que el pipeline de datos |
| Frontend | Next.js 14+ App Router | Deploy rápido en Vercel |
| Gráficos | Recharts o Tremor | Timeline de score sin mucho código |
| Estilos | Tailwind + shadcn/ui | UI pulida en poco tiempo |
| Datos en runtime | JSON/Parquet precomputado | Demo rápida, sin ETL en vivo |

---

## Backend (FastAPI)

### Estructura

```
backend/
  main.py
  routers/
    companies.py
    scores.py
    alerts.py
    explanations.py
  data/                  # symlink o copy de data/processed/
  requirements.txt
```

### Endpoints

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/companies` | Lista con score M24, trajectory, has_alert |
| GET | `/companies/{id}` | Metadatos + score actual |
| GET | `/companies/{id}/timeline` | Serie 24 meses (score, level, momentum, stability) |
| GET | `/companies/{id}/explanation?month=` | Explicación completa con drivers |
| GET | `/groups/{group_id}` | Empresas del holding con scores relativos |
| GET | `/groups/{group_id}/plan` | JSON del plan (`advisor/group_plans/`) y su narrativa `.md`; `status` ∈ plan / no_feasible_levers / single_subsidiary |
| GET | `/companies/{id}/sensitivity` | JSON de sensibilidad (`advisor/company_sensitivity/`) y su narrativa `.md` |
| POST | `/qa` | `{doc_id, intent, args}` → respuesta cerrada de `xray.group_advisor.qa.answer` (nueve intenciones); sin LLM |
| GET | `/alerts` | Feed paginado, filtros severity/type |
| GET | `/alerts/recent?limit=10` | Para widget del dashboard |
| POST | `/alerts/{id}/acknowledge` | Demo: marcar alerta como vista |
| GET | `/health` | Healthcheck para deploy |

### Ejemplo respuesta `/companies`

```json
{
  "companies": [
    {
      "company_id": "COMP_0218",
      "group_id": "GROUP_0113",
      "score": 68,
      "trajectory": "deteriorating",
      "delta_vs_prev": -3,
      "has_active_alert": true,
      "alert_severity": "high"
    }
  ],
  "total": 1286
}
```

Cargar Parquet/JSON al arranque en memoria (dataset pequeño post-agregación).

---

## Frontend (Next.js)

### Pantallas mínimas (obligatorio para demo)

#### 1. Dashboard (`/`)

- Tabla de empresas: score, trayectoria (badge color), delta, alerta
- Filtros: trajectory, severidad, búsqueda por company_id
- Widget superior: *"12 alertas activas · 3 críticas"*
- Orden default: alertas high primero, luego score ascendente (peores primero)

#### 2. Detalle empresa (`/companies/[id]`)

- Gráfico línea: score 24 meses
- Área apilada o líneas: level / momentum / stability
- Tarjeta descomposición: *"68 = Nivel 29 + Momentum 15 + Estabilidad 17"*
- Top 3 drivers con flechas better/worse
- Anotaciones en timeline (inflexión momentum, caída score)
- Bloque recomendaciones si hay alerta activa

#### 3. Monitor (`/alerts`)

- Feed cronológico de alertas
- Filtro por tipo y severidad
- Click → navega a detalle empresa
- Botón "Marcar como vista" (ack)

#### 4. Vista grupo (`/groups/[id]`) — solo si el grupo tiene ≥2 filiales puntuadas

- Barras horizontales: nivel por filial con tramo (rojo/ámbar/verde) y papel (donante/receptora/estructural)
- `G` antes → después (k=1 y k=6), filiales que cambian de tramo, caja comprometida por donante
- Plan paso a paso (`render_plan`): frase de negocio, efecto en receptora y donante, eficiencia por 10.000, restricción activa, evidencia
- «Por qué no más / por qué no otras» y **supuestos en pantalla** («escenario mecánico bajo supuestos explícitos»)
- Sin plan: motivos por filial, sin «todo bien» implícito

#### 2b. Bloque «Qué mueve tu nivel» (en la ficha de empresa)

- Tres palancas top por 1 % y por 10.000 (`render_sensitivity`), con la pendiente y hasta dónde vale
- Frase de cambio de tramo: «Para pasar a verde: −27,3 % de salidas o +34 % de entradas»
- Palancas de negocio etiquetadas como sensibilidad; palancas no evaluables con motivo
- Banner «En el plan de grupo, esta filial recibe apoyo en el paso 1» con enlace a `/groups/[id]`

### UX para el pitch (5 min)

1. **Monitor** — "Esta semana 3 empresas requieren atención"
2. **Detalle deterioro** — Velasco-like: score 68 pero momentum rojo 4 meses
3. **Detalle mejora** — Northbrook-like: score medio pero tendencia fuerte
4. **Explicación** — un click y se ve el porqué; debajo, «Qué mueve tu nivel» (COMP_0007: para verde, −27,3 % de salidas o +34 % de entradas; la cuota no basta)
5. **Grupo** — GROUP_0067: COMP_1048 asume las cuotas de COMP_1275 (12.340 EUR/mes) y esta pasa de 31 a 66,7; supuestos en pantalla; GROUP_0064 como contraejemplo honesto («sin palancas: problema estructural»)
6. **Comprador** — "Embat lo vende como Pulse premium"

---

## Despliegue

| Servicio | Qué | URL |
|---|---|---|
| Vercel | Frontend Next.js | `https://embat-pulse.vercel.app` |
| Railway / Render | Backend FastAPI | `https://embat-pulse-api.onrender.com` |

Variables de entorno frontend:

```
NEXT_PUBLIC_API_URL=https://embat-pulse-api.onrender.com
```

**Requisito del enunciado:** demo que se abra en el navegador del jurado, no notebook local.

---

## Datos en la demo

Precomputar todo en batch antes del deploy:

```bash
python scripts/01_build_monthly_features.py
python scripts/02_compute_scores.py
python scripts/03_generate_explanations.py
python scripts/04_generate_alerts.py
cp data/processed/* backend/data/
```

No ejecutar DuckDB sobre 3,5M filas en el servidor de demo.

---

## Pitch (estructura 5 min)

| Min | Bloque | Mensaje |
|---|---|---|
| 0–1 | Problema | Dos empresas, mismo score en M24, riesgos opuestos |
| 1–2 | Motor | Score = nivel + momentum + estabilidad; anticipa 3 meses |
| 2–3 | Demo en vivo | Monitor → detalle → explicación |
| 3–4 | Producto | Embat Pulse: alertas + recomendaciones sobre datos que ya tienen |
| 4–5 | Comprador + métricas | Embat premium; lead time 2.8m; leaderboard iteración N |

---

## Checklist de entrega

| Requisito enunciado | Estado | Dónde |
|---|---|---|
| Predicción test oculto | CSV leaderboard | `06_export_leaderboard.py` |
| Señal dos direcciones | Momentum + alertas positivas | [scoring.md](./scoring.md) |
| Trayectoria | Componente momentum | [scoring.md](./scoring.md) |
| Explicación | Drivers + descomposición | [explainability.md](./explainability.md) |
| Producto encima | Embat Pulse | Este doc |
| Comprador | Embat premium | Este doc |
| Demo navegable | URL Vercel | Este doc |
| Anticipación (bonus) | `months_ahead` en alertas | [alerts-and-monitoring.md](./alerts-and-monitoring.md) |
| Monitor (bonus) | Pantalla `/alerts` | Este doc |

---

## Estructura final del repo

```
every.hackspain/
├── data/                          # CSV completos (gitignored)
├── data/processed/                # Parquet + JSON generados
├── data_summary/                  # Muestras en git
├── docs/
│   ├── README.md
│   ├── feature-engineering.md
│   ├── scoring.md
│   ├── explainability.md
│   ├── alerts-and-monitoring.md
│   ├── validation.md
│   └── product-and-demo.md
├── scripts/
│   ├── 01_build_monthly_features.py
│   ├── 02_compute_scores.py
│   ├── 03_generate_explanations.py
│   ├── 04_generate_alerts.py
│   ├── 05_validate.py
│   └── 06_export_leaderboard.py
├── backend/
└── frontend/
```

---

## Próximo paso de implementación

1. Implementar `01_build_monthly_features.py` siguiendo [feature-engineering.md](./feature-engineering.md)
2. Encadenar scripts 02–04
3. Levantar API mínima con 3 endpoints
4. Frontend con dashboard + detalle + monitor
5. Deploy y ensayo de pitch
