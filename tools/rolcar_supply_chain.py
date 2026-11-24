#!/usr/bin/env python3
"""
rolcar_supply_chain.py
======================
Módulo de Simulación de Cadena de Suministro y Planeación de Materiales (MRP)
para la red de 27 sucursales de Rolcar en Aguascalientes dentro de StreetVulkan.

Calcula:
  1. Niveles de Stock de Seguridad (Safety Stock - SS) con nivel de servicio 95%.
  2. Punto de Reorden (Reorder Point - ROP) por SKU en cada sucursal.
  3. Detección de riesgo de desabasto (Stockout Alerts).
  4. Órdenes de Traspaso / Reabastecimiento desde el CEDIS Central hacia sucursales.
  5. Despacho y optimización de ruta de camiones de reparto por proximidad geográfica.
"""

import json
import math
import os
import random

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BRANCHES_FILE = os.path.join(ROOT, "models", "rolcar_aguascalientes.json")
OUTPUT_REPORT = os.path.join(ROOT, "build", "rolcar_supply_chain_report.json")

# Catálogo estándar de refacciones automotrices (SKUs) de alta rotación
SKU_CATALOG = [
    {"sku": "ROL-BRK-101", "name": "Juego de Balatas Cerámicas", "cost_mxn": 650.0, "unit": "juego"},
    {"sku": "ROL-FLT-202", "name": "Filtro de Aceite Sintético", "cost_mxn": 180.0, "unit": "pieza"},
    {"sku": "ROL-SPK-303", "name": "Bujías de Iridio (Set 4)", "cost_mxn": 420.0, "unit": "set"},
    {"sku": "ROL-SHK-404", "name": "Amortiguador Delantero Gas", "cost_mxn": 1150.0, "unit": "pieza"},
    {"sku": "ROL-BLT-505", "name": "Banda de Distribución / Tiempo", "cost_mxn": 520.0, "unit": "pieza"},
]

# Parámetros logísticos
SERVICE_LEVEL_Z = 1.65  # 95% de nivel de servicio (probabilidad de no quiebre)
LEAD_TIME_DAYS = 1.5    # Tiempo de entrega promedio CEDIS -> Sucursal en Ags (días)


def run_supply_chain_planner():
    if not os.path.exists(BRANCHES_FILE):
        print(f"[ERROR] No se encontró el archivo de sucursales en: {BRANCHES_FILE}")
        return

    with open(BRANCHES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    branches = data.get("branches", [])
    if not branches:
        print("[ERROR] No se encontraron sucursales en el archivo JSON.")
        return

    # Asignamos la primera sucursal o la más céntrica como CEDIS Central
    # (Por ejemplo: 'REFACCIONARIA ROGELIO MATRIZ' o la primera del índice)
    cedis = branches[0]
    for b in branches:
        if "MATRIZ" in b["name"].upper():
            cedis = b
            break

    print("================================================================================")
    print(" 🚗 STREETVULKAN: SIMULADOR DE CADENA DE SUMINISTRO ROLCAR (AGUASCALIENTES)")
    print(f" CEDIS Hub Central: {cedis['name']} ({cedis['address']})")
    print(f" Red de Distribución: {len(branches)} sucursales conectadas")
    print("================================================================================\n")

    random.seed(42)  # Determinista para pruebas reproducibles

    replenishment_orders = []
    total_skus_tracked = len(branches) * len(SKU_CATALOG)
    stockout_risks = 0
    total_reorder_cost = 0.0

    branch_kpis = []

    for branch in branches:
        # Calcular distancia euclidiana al CEDIS (en metros según coordenadas StreetVulkan)
        dx = branch["x"] - cedis["x"]
        dz = branch["z"] - cedis["z"]
        dist_km = math.sqrt(dx * dx + dz * dz) / 1000.0

        branch_orders = []

        for item in SKU_CATALOG:
            # Demanda diaria promedio (mu) y desviación estándar (sigma)
            avg_daily_demand = random.uniform(3.0, 12.0)
            std_daily_demand = avg_daily_demand * 0.35  # 35% de volatilidad

            # Cálculo de fórmulas estándar de Supply Chain (MRP):
            # Safety Stock = Z * sigma * sqrt(LeadTime)
            safety_stock = math.ceil(SERVICE_LEVEL_Z * std_daily_demand * math.sqrt(LEAD_TIME_DAYS))
            
            # Punto de Reorden (ROP) = (Demanda Diaria * LeadTime) + Safety Stock
            reorder_point = math.ceil((avg_daily_demand * LEAD_TIME_DAYS) + safety_stock)

            # Stock actual simulado en piso de venta
            current_stock = random.randint(1, int(reorder_point * 1.6))

            # ¿Disparar orden de reabastecimiento?
            if current_stock <= reorder_point:
                stockout_risks += 1
                # Cantidad a pedir para restablecer a nivel objetivo (Target Stock = ROP + Lote de reposición)
                lot_size = math.ceil(avg_daily_demand * 4)  # 4 días de cobertura
                order_qty = (reorder_point + lot_size) - current_stock
                cost = order_qty * item["cost_mxn"]
                total_reorder_cost += cost

                urgency = "CRÍTICO" if current_stock < safety_stock else "NORMAL"

                order_info = {
                    "sku": item["sku"],
                    "product": item["name"],
                    "current_stock": current_stock,
                    "safety_stock": safety_stock,
                    "reorder_point": reorder_point,
                    "order_qty": order_qty,
                    "cost_mxn": cost,
                    "urgency": urgency
                }
                branch_orders.append(order_info)

        if branch_orders:
            replenishment_orders.append({
                "branch_name": branch["name"],
                "address": branch["address"],
                "dist_cedis_km": round(dist_km, 2),
                "orders": branch_orders
            })

        branch_kpis.append({
            "branch": branch["name"],
            "dist_km": round(dist_km, 2),
            "pending_orders": len(branch_orders)
        })

    # Ordenar rutas de entrega por distancia al CEDIS (optimización de última milla)
    replenishment_orders.sort(key=lambda x: x["dist_cedis_km"])

    print(f"📊 RESUMEN EJECUTIVO DE PLANEACIÓN DE MATERIALES:")
    print(f"  • Total de puntos de control (SKU x Sucursales): {total_skus_tracked}")
    print(f"  • Alertas de reorden disparadas: {stockout_risks} ({(stockout_risks/total_skus_tracked)*100:.1f}% de la red)")
    print(f"  • Sucursales que requieren abastecimiento hoy: {len(replenishment_orders)} / {len(branches)}")
    print(f"  • Inversión requerida de traspaso CEDIS: ${total_reorder_cost:,.2f} MXN\n")

    print("🚛 TOP 5 SUCURSALES PRIORITARIAS PARA RUTA DE REPARTO (CERCANÍA Y URGENCIA):")
    for idx, r in enumerate(replenishment_orders[:5], 1):
        criticos = sum(1 for o in r["orders"] if o["urgency"] == "CRÍTICO")
        print(f"  {idx}. {r['branch_name']} ({r['dist_cedis_km']} km del CEDIS)")
        print(f"     Dirección: {r['address']}")
        print(f"     Líneas de pedido: {len(r['orders'])} refacciones | Críticos: {criticos}")
        for o in r["orders"][:2]:
            print(f"       -> [{o['urgency']}] {o['sku']} ({o['product']}): Stock {o['current_stock']} <= ROP {o['reorder_point']}. Solicitar {o['order_qty']} uds.")
        print()

    # Guardar reporte JSON estructurado
    os.makedirs(os.path.dirname(OUTPUT_REPORT), exist_ok=True)
    report_data = {
        "simulation": "StreetVulkan Supply Chain Logistics Engine",
        "cedis_hub": cedis["name"],
        "total_branches": len(branches),
        "total_skus_tracked": total_skus_tracked,
        "stockout_alerts": stockout_risks,
        "total_reorder_cost_mxn": round(total_reorder_cost, 2),
        "replenishment_routes": replenishment_orders
    }
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    print(f"✅ Reporte guardado exitosamente en: {OUTPUT_REPORT}")
    print("================================================================================")


if __name__ == "__main__":
    run_supply_chain_planner()
