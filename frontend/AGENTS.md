# Frontend: integración y verificación

- Ejecutar desde `frontend/`: `npm ci`, `npm test`, `npm run lint`, `npm run build`, `npm run typecheck`.
- Navegador: `npx playwright install chromium`, después `npm run build` y `npm run test:e2e`. Playwright crea dos servidores de producción temporales en los puertos 3106 y 3108: uno con fixtures explícitos y otro sin datos. No reutiliza ni modifica archivos reales. Comprueba escritorio, móvil, tablet y accesibilidad automatizada.
- Arranque normal: `npm run dev`. La única entrada de datos es `getCompanyDetail(companyId)` en `services/companyData.ts`, que valida JSON de `public/generated/companies/<company_id>.json` en el servidor Next.js. No hay fallback a fixtures. La ruta es dinámica y relee los archivos en cada petición.
- Integración con Data: `../docs/frontend-data-contract.md` incluye el contrato completo y un JSON validado por tests. `npm run validate:generated` valida exportaciones reales. `COMPANY_ANALYSIS_DIR` permite un directorio alternativo absoluto.
- Sin JSON se muestra «Datos de análisis todavía no disponibles». Un JSON incompatible muestra un estado de revisión sin puntuaciones.
- Desarrollo ficticio exclusivamente mediante `npm run dev:fixtures -- --port 3107`: el lanzador exporta `tests/fixtures/companyDetails.ts` a un directorio temporal aislado. No escribe en `public/generated`. Los datos ficticios requieren habilitación explícita de `COMPANY_DATA_MODE=fixtures`; no usarla en producción.
- Componente integrable: `components/insights/CompanyInsights.tsx`, estilos en `insights.module.css`. La navegación global y Portfolio siguen fuera de esta rama. Hay un layout mínimo independiente.
- `types/companyDetail.ts` contiene un único esquema runtime Zod del que se infiere `CompanyDetail`. Los scores son enteros 0–100 suministrados por Data; dimensiones/cobertura son 0–100; importes en EUR, no céntimos; fechas ISO. `null` significa dato no evaluable, nunca cero implícito.
- `lib/healthScore.ts` centraliza pesos provisionales y etiquetas, no calcula puntuaciones. La UI muestra los pesos efectivos de `health_score_model` recibidos del pipeline.
- Origen de la caja separa bruto, neto, circulación, operación, apoyo y no identificado. Las muestras no son conciliaciones completas.
- Tiempo financiado muestra medianas independientes. AR es plazo concedido; AP, plazo recibido. No interpretar más retraso a proveedores como una mejora.
- El simulador solo selecciona resultados precalculados por coincidencia exacta. No calcula ni interpola scores; sin coincidencia se informa de la ausencia. Mantener «Escenario, no predicción.».
- Toda la interfaz está en español salvo nombres de producto y los términos solicitados Health Score/Momentum. No cargar fuentes ni recursos externos durante la demo.
- Next 16.3.4 está fijado porque Next 15.5.25 dependía de una versión vulnerable de PostCSS. Auditar dependencias antes de cambiar versiones.
