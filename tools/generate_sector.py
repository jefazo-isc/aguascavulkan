#!/usr/bin/env python3
"""
generate_sector.py FASE 2b - Árboles visibles + relleno en parques
"""
import os, math, random
from geo_dem import geo_to_meters, TerrainElevation, MeshElevationGrid
from osm_extractor import fetch_osm_data, parse_osm_data
from cv_patch_analyzer import SatellitePatchAnalyzer
from open_buildings_fetcher import merge_and_densify_buildings
from procedural_props import make_building_3d, make_zebra_crossing_3d, make_traffic_signal_3d, make_tree_3d, make_grass_patch, make_sidewalk_3d, make_street_corner_sign_3d
from bridge_generator import make_civil_bridge_3d, make_pedestrian_bridge_3d, make_underground_pass_3d
from celestial_stars import generate_aguascalientes_night_sky
from gltf_writer import export_glb_mesh, export_traffic_signals_json, export_chunks_json

def _point_to_segment_dist(px,pz,ax,az,bx,bz):
    dx,dz=bx-ax,bz-az
    len_sq=dx*dx+dz*dz
    if len_sq<1e-6: return math.hypot(px-ax,pz-az)
    t=max(0.0,min(1.0,((px-ax)*dx+(pz-az)*dz)/len_sq))
    return math.hypot(px-(ax+t*dx),pz-(az+t*dz))

class RoadSpatialIndex:
    def __init__(self, highway_pts_m, cell_size=40.0):
        self.cell_size = cell_size
        self.grid = {}
        for pts in highway_pts_m:
            for i in range(len(pts) - 1):
                p0_x, p0_z = pts[i]
                p1_x, p1_z = pts[i+1]
                min_x = min(p0_x, p1_x) - 7.0
                max_x = max(p0_x, p1_x) + 7.0
                min_z = min(p0_z, p1_z) - 7.0
                max_z = max(p0_z, p1_z) + 7.0
                c_x0, c_x1 = int(min_x // cell_size), int(max_x // cell_size)
                c_z0, c_z1 = int(min_z // cell_size), int(max_z // cell_size)
                seg = (p0_x, p0_z, p1_x, p1_z)
                for cx in range(c_x0, c_x1 + 1):
                    for cz in range(c_z0, c_z1 + 1):
                        key = (cx, cz)
                        if key not in self.grid:
                            self.grid[key] = []
                        self.grid[key].append(seg)

    def is_near(self, x, z, threshold=6.0):
        cell = (int(x // self.cell_size), int(z // self.cell_size))
        candidates = self.grid.get(cell, [])
        for ax, az, bx, bz in candidates:
            if _point_to_segment_dist(x, z, ax, az, bx, bz) < threshold:
                return True
        return False

def is_near_building(x,z,buildings,threshold=8.0):
    for b in buildings:
        poly=b.get("polygon") or b.get("poly") or []
        if not poly: continue
        # centroide simple
        cx=sum(p[0] for p in poly)/len(poly)
        cz=sum(p[1] for p in poly)/len(poly)
        if math.hypot(x-cx,z-cz)<threshold:
            return True
    return False

def point_in_polygon(x, z, poly):
    n = len(poly)
    inside = False
    p1x, p1z = poly[0]
    for i in range(n + 1):
        p2x, p2z = poly[i % n]
        if z > min(p1z, p2z):
            if z <= max(p1z, p2z):
                if x <= max(p1x, p2x):
                    if p1z != p2z:
                        xinters = (z - p1z) * (p2x - p1x) / (p2z - p1z) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1z = p2x, p2z
    return inside

class BuildingSpatialIndex:
    def __init__(self, buildings, cell_size=40.0):
        self.cell_size = cell_size
        self.grid = {}
        for b in buildings:
            poly = b.get("polygon") or b.get("poly") or []
            if not poly: continue
            min_x = min(p[0] for p in poly) - 6.0
            max_x = max(p[0] for p in poly) + 6.0
            min_z = min(p[1] for p in poly) - 6.0
            max_z = max(p[1] for p in poly) + 6.0
            c_x0, c_x1 = int(min_x // cell_size), int(max_x // cell_size)
            c_z0, c_z1 = int(min_z // cell_size), int(max_z // cell_size)
            item = (poly, min_x, max_x, min_z, max_z)
            for cx in range(c_x0, c_x1 + 1):
                for cz in range(c_z0, c_z1 + 1):
                    key = (cx, cz)
                    if key not in self.grid:
                        self.grid[key] = []
                    self.grid[key].append(item)

    def is_inside_or_near(self, x, z, min_dist=6.0):
        cell = (int(x // self.cell_size), int(z // self.cell_size))
        candidates = self.grid.get(cell, [])
        for poly, min_x, max_x, min_z, max_z in candidates:
            if x < min_x or x > max_x or z < min_z or z > max_z:
                continue
            if point_in_polygon(x, z, poly):
                return True
            for px, pz in poly:
                if math.hypot(x - px, z - pz) < min_dist:
                    return True
        return False

def generate_sector():
    print("="*65); print("  GENERACIÓN FASE 2c - ÁRBOLES REALES Y UBICACIÓN EXACTA"); print("="*65)
    origin_lat=21.8807; origin_lon=-102.2965
    min_lon=-102.3110; max_lon=-102.2815; min_lat=21.8690; max_lat=21.8940
    min_x,max_z=geo_to_meters(min_lat,min_lon,origin_lat,origin_lon)
    max_x,min_z=geo_to_meters(max_lat,max_lon,origin_lat,origin_lon)
    pad=120.0; x0,x1=min_x-pad,max_x+pad; z0,z1=min_z-pad,max_z+pad
    terrain=TerrainElevation(min_lat,max_lat,min_lon,max_lon,nx=40,ny=40,origin_lat=origin_lat,origin_lon=origin_lon)
    osm_xml=fetch_osm_data(min_lon,min_lat,max_lon,max_lat)
    nodes,osm_buildings,highways,traffic_signals,crossings,intersections,osm_trees,park_polygons,civil_bridges,pedestrian_bridges,tunnels=parse_osm_data(osm_xml)
    sat_image_path="assets/satellite.png"
    patch_analyzer=SatellitePatchAnalyzer(sat_image_path,x0,z0,x1,z1)
    cv_buildings=patch_analyzer.analyze_patches_for_buildings(patch_size=256,stride=192)
    all_buildings=merge_and_densify_buildings(osm_buildings,cv_buildings,highways,x0,x1,z0,z1,origin_lat=origin_lat,origin_lon=origin_lon)
    all_vertices=[]; traffic_metadata=[]
    print("[Malla] Terreno..."); cols,rows=128,128; dx=(x1-x0)/cols; dz=(z1-z0)/rows; grid_pts=[]
    for r in range(rows+1):
        for c in range(cols+1):
            px=x0+c*dx; pz=z0+r*dz; py=terrain.get_ground_elevation(px,pz); u=(px-x0)/(x1-x0); v=(pz-z0)/(z1-z0); grid_pts.append((px,py,pz,u,v))
    mesh_grid=MeshElevationGrid(x0,z0,x1,z1,cols,rows,grid_pts)
    norm_up=(0.0,1.0,0.0); terrain_col=(1.0,1.0,1.0,0.0)
    for r in range(rows):
        for c in range(cols):
            idx0=r*(cols+1)+c; idx1=idx0+1; idx2=(r+1)*(cols+1)+c; idx3=idx2+1
            p0,p1,p2,p3=grid_pts[idx0],grid_pts[idx1],grid_pts[idx2],grid_pts[idx3]
            all_vertices.append(((p0[0],p0[1],p0[2]),norm_up,(p0[3],p0[4]),terrain_col,0.0))
            all_vertices.append(((p1[0],p1[1],p1[2]),norm_up,(p1[3],p1[4]),terrain_col,0.0))
            all_vertices.append(((p2[0],p2[1],p2[2]),norm_up,(p2[3],p2[4]),terrain_col,0.0))
            all_vertices.append(((p1[0],p1[1],p1[2]),norm_up,(p1[3],p1[4]),terrain_col,0.0))
            all_vertices.append(((p3[0],p3[1],p3[2]),norm_up,(p3[3],p3[4]),terrain_col,0.0))
            all_vertices.append(((p2[0],p2[1],p2[2]),norm_up,(p2[3],p2[4]),terrain_col,0.0))
    print(f"[Malla] {len(highways)} vías..."); asphalt_col=(0.22,0.22,0.24,0.95); curb_col=(0.45,0.45,0.46,0.95); road_clearance=0.12
    highway_pts_m=[]
    for coords,tags,refs in highways:
        if len(coords)<2: continue
        pts_m=[geo_to_meters(lat,lon,origin_lat,origin_lon) for lat,lon in coords]; highway_pts_m.append(pts_m)
        road_w=7.5
        if tags.get('highway') in ('primary','trunk'): road_w=11.0
        elif tags.get('highway')=='secondary': road_w=9.0
        half_w=road_w*0.5
        for i in range(len(pts_m)-1):
            p0=pts_m[i]; p1=pts_m[i+1]; dx_r=p1[0]-p0[0]; dz_r=p1[1]-p0[1]; rlen=math.hypot(dx_r,dz_r)
            if rlen<0.1: continue
            px_norm=-dz_r/rlen; pz_norm=dx_r/rlen; sub_steps=max(1,int(math.ceil(rlen/16.0)))
            for s in range(sub_steps):
                t_start=s/float(sub_steps); t_end=(s+1)/float(sub_steps)
                sp0_x=p0[0]+t_start*dx_r; sp0_z=p0[1]+t_start*dz_r; sp1_x=p0[0]+t_end*dx_r; sp1_z=p0[1]+t_end*dz_r
                y0=mesh_grid.get_mesh_height(sp0_x,sp0_z)+road_clearance; y1=mesh_grid.get_mesh_height(sp1_x,sp1_z)+road_clearance
                q0=(sp0_x-half_w*px_norm,y0,sp0_z-half_w*pz_norm); q1=(sp0_x+half_w*px_norm,y0,sp0_z+half_w*pz_norm)
                q2=(sp1_x+half_w*px_norm,y1,sp1_z+half_w*pz_norm); q3=(sp1_x-half_w*px_norm,y1,sp1_z-half_w*pz_norm)
                all_vertices.append((q0,norm_up,(0,0),asphalt_col,0.0)); all_vertices.append((q1,norm_up,(0,0),asphalt_col,0.0)); all_vertices.append((q2,norm_up,(0,0),asphalt_col,0.0))
                all_vertices.append((q0,norm_up,(0,0),asphalt_col,0.0)); all_vertices.append((q2,norm_up,(0,0),asphalt_col,0.0)); all_vertices.append((q3,norm_up,(0,0),asphalt_col,0.0))
                base_y0=y0-road_clearance; base_y1=y1-road_clearance; b_r0=(q1[0],base_y0,q1[2]); b_r1=(q2[0],base_y1,q2[2])
                all_vertices.append((q1,(px_norm,0,pz_norm),(0,0),curb_col,0.0)); all_vertices.append((b_r0,(px_norm,0,pz_norm),(0,0),curb_col,0.0)); all_vertices.append((b_r1,(px_norm,0,pz_norm),(0,0),curb_col,0.0))
                all_vertices.append((q1,(px_norm,0,pz_norm),(0,0),curb_col,0.0)); all_vertices.append((b_r1,(px_norm,0,pz_norm),(0,0),curb_col,0.0)); all_vertices.append((q2,(px_norm,0,pz_norm),(0,0),curb_col,0.0))
                b_l0=(q0[0],base_y0,q0[2]); b_l1=(q3[0],base_y1,q3[2])
                all_vertices.append((q3,(-px_norm,0,-pz_norm),(0,0),curb_col,0.0)); all_vertices.append((b_l1,(-px_norm,0,-pz_norm),(0,0),curb_col,0.0)); all_vertices.append((b_l0,(-px_norm,0,-pz_norm),(0,0),curb_col,0.0))
                all_vertices.append((q3,(-px_norm,0,-pz_norm),(0,0),curb_col,0.0)); all_vertices.append((b_l0,(-px_norm,0,-pz_norm),(0,0),curb_col,0.0)); all_vertices.append((q0,(-px_norm,0,-pz_norm),(0,0),curb_col,0.0))
                # Banquetas elevadas 0.15m a ambos lados de la vía
                sw_verts = make_sidewalk_3d(sp0_x, sp0_z, sp1_x, sp1_z, y0, y1, half_w, px_norm, pz_norm, sidewalk_w=1.60, curb_h=0.15)
                all_vertices.extend(sw_verts)

    print(f"[Malla Puentes] {len(civil_bridges)} viaductos/puentes vehiculares...")
    for coords, tags, refs in civil_bridges:
        if len(coords) < 2: continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        highway_pts_m.append(pts_m)
        road_w = 9.0
        if tags.get('highway') in ('primary', 'trunk') or tags.get('bridge') == 'viaduct': road_w = 11.5
        layer_lvl = int(tags.get('layer', '1') or 1)
        clearance = 5.5 * max(1, layer_lvl)
        b_verts = make_civil_bridge_3d(pts_m, road_w=road_w, clearance_h=clearance, mesh_grid=mesh_grid)
        all_vertices.extend(b_verts)

    print(f"[Malla Puentes] {len(pedestrian_bridges)} puentes peatonales elevados...")
    for coords, tags, refs in pedestrian_bridges:
        if len(coords) < 2: continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        p_verts = make_pedestrian_bridge_3d(pts_m, width=2.4, clearance_h=5.4, mesh_grid=mesh_grid)
        all_vertices.extend(p_verts)

    print(f"[Malla Túneles] {len(tunnels)} pasos a desnivel subterráneos/túneles...")
    for coords, tags, refs in tunnels:
        if len(coords) < 2: continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        highway_pts_m.append(pts_m)
        road_w = 9.5
        if tags.get('highway') in ('primary', 'trunk'): road_w = 11.5
        tun_verts = make_underground_pass_3d(pts_m, road_w=road_w, depth_m=5.4, mesh_grid=mesh_grid)
        all_vertices.extend(tun_verts)

    print(f"[Malla] {len(intersections)} letreros de esquina en vialidades...")
    # Build list of named highway segment midpoints for name lookup
    named_highway_pts = []
    for coords, tags, refs in highways:
        if len(coords) < 2:
            continue
        pts_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in coords]
        name = tags.get('name')
        if name:
            mid_idx = len(pts_m) // 2
            mx, mz = pts_m[mid_idx]
            named_highway_pts.append((mx, mz, name))
    # Helper to find nearest street name for an intersection point
    def _nearest_street_name(ix_m, iz_m, max_dist=15.0):
        best_name = None
        best_dist = 1e9
        for mx, mz, nm in named_highway_pts:
            d = math.hypot(ix_m - mx, iz_m - mz)
            if d < best_dist and d <= max_dist:
                best_dist = d
                best_name = nm
        return best_name if best_name else "CALLE"

    corner_sign_count = 0
    for ix, (ilat, ilon) in enumerate(intersections):
        ix_m, iz_m = geo_to_meters(ilat, ilon, origin_lat, origin_lon)
        if x0 <= ix_m <= x1 and z0 <= iz_m <= z1:
            # Optional density filter: keep every other intersection
            if ix % 2 != 0:
                continue
            igy = mesh_grid.get_mesh_height(ix_m, iz_m) + road_clearance
            # Position sign offset 4.5m from intersection center
            st_name = _nearest_street_name(ix_m, iz_m)
            corner_verts = make_street_corner_sign_3d(ix_m + 4.5, igy, iz_m + 4.5,
                                                      street_name=st_name,
                                                      dir_angle=(ix * 1.57) % 6.28)
            all_vertices.extend(corner_verts)
            corner_sign_count += 1

    print("[Malla] Cebras...")
    for lat,lon,tags,nid in crossings:
        cx,cz=geo_to_meters(lat,lon,origin_lat,origin_lon)
        if x0<=cx<=x1 and z0<=cz<=z1:
            gy=mesh_grid.get_mesh_height(cx,cz)+road_clearance+0.03
            zebra_verts=make_zebra_crossing_3d(cx,gy,cz,road_dir_angle=0.0,road_width=8.0)
            all_vertices.extend(zebra_verts)
    print(f"[Malla] {len(traffic_signals)} semáforos con letreros verdes superiores...")
    sig_counter=0
    for idx,(lat,lon,tags,nid) in enumerate(traffic_signals):
        sx,sz=geo_to_meters(lat,lon,origin_lat,origin_lon)
        if x0<=sx<=x1 and z0<=sz<=z1:
            gy=mesh_grid.get_mesh_height(sx,sz)+road_clearance
            phase=0 if (idx%2==0) else 1; inter_id=idx//2; dir_angle=(idx*1.57)%6.28
            st_name = _nearest_street_name(sx, sz)
            global_offset=len(all_vertices)
            sig_verts,meta=make_traffic_signal_3d(sig_counter,inter_id,phase,sx,gy,sz,dir_angle,street_name=st_name)
            if "lenses" in meta:
                for lens_name in meta["lenses"]: meta["lenses"][lens_name]["start"]+=global_offset
            all_vertices.extend(sig_verts); traffic_metadata.append(meta); sig_counter+=1
    print(f"[Malla] {len(all_buildings)} edificios con ventanas emisivas y clasificación real...")
    for b in all_buildings:
        roof_col=b.get("roof_color") or (0.85,0.82,0.78)
        wall_col=b.get("wall_color")
        cat=b.get("category") or b.get("type") or b.get("class") or "residencial"
        b_verts=make_building_3d(b["polygon"],b["height"],mesh_grid.get_mesh_height,roof_color=roof_col,wall_color_override=wall_col,category=cat,x0_map=x0,z0_map=z0,x1_map=x1,z1_map=z1)
        all_vertices.extend(b_verts)

    # VEGETACIÓN PRECISA: CV + OSM trees + parques
    print("[Malla Vegetación] Procesando árboles exactos de CV y OSM...")
    trees_planted = 0
    bldg_spatial_index = BuildingSpatialIndex(all_buildings, cell_size=50.0)
    road_spatial_index = RoadSpatialIndex(highway_pts_m, cell_size=40.0)

    # 1. Árboles reales etiquetados en OSM
    for lat, lon, tags, nid in osm_trees:
        tx, tz = geo_to_meters(lat, lon, origin_lat, origin_lon)
        if x0 <= tx <= x1 and z0 <= tz <= z1:
            if not road_spatial_index.is_near(tx, tz, threshold=4.0) and not bldg_spatial_index.is_inside_or_near(tx, tz, min_dist=4.0):
                gy = mesh_grid.get_mesh_height(tx, tz) + 0.02
                tree_verts = make_tree_3d(tx, gy, tz, radius=2.0 + random.random()*0.5, species=random.randint(0, 1))
                all_vertices.extend(tree_verts)
                trees_planted += 1

    # 2. Árboles en Parques y Zonas Verdes de OSM (leisure=park, landuse=grass)
    for park_coords, tags in park_polygons:
        poly_m = [geo_to_meters(lat, lon, origin_lat, origin_lon) for lat, lon in park_coords]
        if not poly_m: continue
        px_min = min(p[0] for p in poly_m); px_max = max(p[0] for p in poly_m)
        pz_min = min(p[1] for p in poly_m); pz_max = max(p[1] for p in poly_m)
        # Poblar el parque con grilla regular de árboles
        step = 12.0
        curr_x = px_min + 6.0
        while curr_x < px_max:
            curr_z = pz_min + 6.0
            while curr_z < pz_max:
                rx = curr_x + random.uniform(-3.0, 3.0)
                rz = curr_z + random.uniform(-3.0, 3.0)
                if x0 <= rx <= x1 and z0 <= rz <= z1:
                    if point_in_polygon(rx, rz, poly_m):
                        if not road_spatial_index.is_near(rx, rz, threshold=4.5) and not bldg_spatial_index.is_inside_or_near(rx, rz, min_dist=4.0):
                            gy = mesh_grid.get_mesh_height(rx, rz) + 0.02
                            tree_verts = make_tree_3d(rx, gy, rz, radius=1.8 + random.random()*0.8, species=random.randint(0, 1))
                            all_vertices.extend(tree_verts)
                            trees_planted += 1
                curr_z += step
            curr_x += step

    # 3. Detección por visión por computadora (CV) filtrando con Point-In-Polygon estricto
    try:
        veg_patches = patch_analyzer.detect_vegetation_patches()
    except Exception as e:
        print(f"[CV Vegetación] Aviso: {e}"); veg_patches = []

    print(f"[CV Vegetación] Analizando {len(veg_patches)} parches de vegetación...")
    for t in veg_patches:
        tx = t["x"]; tz = t["z"]
        if x0 <= tx <= x1 and z0 <= tz <= z1:
            if not road_spatial_index.is_near(tx, tz, threshold=5.0):
                if not bldg_spatial_index.is_inside_or_near(tx, tz, min_dist=6.0):
                    gy = mesh_grid.get_mesh_height(tx, tz) + 0.02
                    tree_verts = make_tree_3d(tx, gy, tz, radius=min(2.5, max(1.5, t["radius"])), species=random.randint(0, 1))
                    all_vertices.extend(tree_verts)
                    trees_planted += 1

    print(f"[Malla Vegetación] TOTAL Árboles realistas plantados: {trees_planted}")

    # DOMO CELESTE ESTELAR REAL DE AGUASCALIENTES
    print("[Malla Estrellas] Generando estrellas reales del cielo nocturno de Aguascalientes...")
    center_map_x = (x0 + x1) * 0.5
    center_map_z = (z0 + z1) * 0.5
    star_verts = generate_aguascalientes_night_sky(dome_radius=1850.0, center_x=center_map_x, center_z=center_map_z, center_y=150.0)
    all_vertices.extend(star_verts)

    os.makedirs("models", exist_ok=True)
    glb_out = "models/aguascalientes_sector1.glb"
    json_out = "models/traffic_signals.json"
    chunks_out = "models/chunks.json"

    # Exportar chunks (reordena all_vertices in-place, devuelve mapeo old→new)
    print("[Chunks] Organizando vértices por chunks de 128m...")
    old_to_new = export_chunks_json(chunks_out, all_vertices)

    # Reubicar offsets de lentes de semáforos al nuevo orden de vértices
    if old_to_new:
        remapped = 0
        for meta in traffic_metadata:
            for lens_name, lens in meta.get("lenses", {}).items():
                old_start = lens["start"]
                # Reubicar cada vértice del rango [old_start, old_start+count)
                new_start = old_to_new.get(old_start, old_start)
                lens["start"] = new_start
                remapped += 1
        print(f"[Chunks] Reubicados {remapped} lentes de semáforos al nuevo orden")

    export_glb_mesh(glb_out, all_vertices)
    export_traffic_signals_json(json_out, traffic_metadata)
    print("="*65)
    print(f"  FASE 3 COMPLETA! {trees_planted} árboles | chunks exportados")
    print("="*65)

if __name__=="__main__": generate_sector()
