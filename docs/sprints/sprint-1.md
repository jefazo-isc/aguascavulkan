# Sprint 1 — Estabilización web y DevOps

- **Fecha:** 2026-11-25
- **Milestone:** [Sprint 1 — Estabilización web y DevOps](https://github.com/jefazo-isc/aguascavulkan/milestone/1)
- **Objetivo:** que la demo web cargue la ciudad real y que cada cambio se valide y publique automáticamente.

> Contexto: antes de este sprint el proyecto avanzó sin un proceso Scrum formal (fase previa: motor nativo C/Vulkan, pipeline geoespacial y primera migración web). El Sprint 1 es el primero que se gestiona con backlog, milestones y tablero.

## Incremento entregado

| Issue | Resultado | Responsable |
| :--- | :--- | :--- |
| [#1](https://github.com/jefazo-isc/aguascavulkan/issues/1) | El sector 0,0 vuelve a cargar (bug de TDZ que forzaba la escena de respaldo). | @MiguelAngelBatres |
| [#2](https://github.com/jefazo-isc/aguascavulkan/issues/2) | Autos sobre la red vial real, con semáforos y seguimiento, en WebGL2 y WebGPU. | @MiguelAngelBatres |
| [#3](https://github.com/jefazo-isc/aguascavulkan/issues/3) | Mapa base de toda la ciudad: terreno DEM y 48,640 calles. | @MiguelAngelBatres |
| [#4](https://github.com/jefazo-isc/aguascavulkan/issues/4) | 325,610 edificios de Overture como capa LOD. | @MiguelAngelBatres |
| [#5](https://github.com/jefazo-isc/aguascavulkan/issues/5) | Prueba E2E en CI y despliegue a Pages condicionado al CI. | @MiguelAngelBatres |
| [#6](https://github.com/jefazo-isc/aguascavulkan/issues/6) | Pruebas automatizadas de tráfico, mapa base y edificios (49 en verde). | @MiguelAngelBatres |

## Pendiente para el Sprint 2

- Sectores GLB detallados fuera de Pages ([#7](https://github.com/jefazo-isc/aguascavulkan/issues/7)).
- Protección de la rama `main` ([#8](https://github.com/jefazo-isc/aguascavulkan/issues/8)).
- Errores 404 de sectores no publicados en desarrollo local ([#10](https://github.com/jefazo-isc/aguascavulkan/issues/10)).
- Lentes 3D de semáforos sin sincronizar con la fase ([#11](https://github.com/jefazo-isc/aguascavulkan/issues/11)).
