#!/usr/bin/env python3
"""
cv_patch_analyzer.py FASE 2b - Más verde
Baja umbral para Aguascalientes beige
"""
import os, cv2, numpy as np, random, math

class SatellitePatchAnalyzer:
    def __init__(self, image_path, x0, z0, x1, z1):
        self.image_path=image_path; self.x0=x0; self.z0=z0; self.x1=x1; self.z1=z1
        if os.path.exists(image_path):
            self.img=cv2.imread(image_path); self.height,self.width=self.img.shape[:2]
            print(f"[OpenCV] Cargada ortofoto satelital: {self.width}x{self.height} px")
        else:
            self.img=None; self.height,self.width=1024,1024
            print(f"[OpenCV] Aviso: No se encontró {image_path}, modo simulado.")

    def meters_to_pixel(self,x,z):
        u=(x-self.x0)/(self.x1-self.x0); v=(z-self.z0)/(self.z1-self.z0)
        px=int(np.clip(u*(self.width-1),0,self.width-1)); py=int(np.clip(v*(self.height-1),0,self.height-1))
        return px,py
    def pixel_to_meters(self,px,py):
        u=px/float(self.width-1); v=py/float(self.height-1)
        x=self.x0+u*(self.x1-self.x0); z=self.z0+v*(self.z1-self.z0)
        return x,z
    def sample_roof_color(self,polygon_meters):
        if self.img is None or len(polygon_meters)<3: return (0.85,0.82,0.78)
        pts_px=[self.meters_to_pixel(p[0],p[1]) for p in polygon_meters]
        pts_np=np.array(pts_px,dtype=np.int32)
        x,y,w,h=cv2.boundingRect(pts_np)
        if w<=0 or h<=0 or x+w>self.width or y+h>self.height: return (0.85,0.82,0.78)
        mask=np.zeros((h,w),dtype=np.uint8); cv2.drawContours(mask,[pts_np-[x,y]],-1,255,-1)
        roi=self.img[y:y+h,x:x+w]; mean_bgr=cv2.mean(roi,mask=mask)[:3]
        return (mean_bgr[2]/255.0,mean_bgr[1]/255.0,mean_bgr[0]/255.0)

    def analyze_patches_for_buildings(self,patch_size=256,stride=192,min_area_m2=20.0,max_area_m2=4500.0):
        if self.img is None: return []
        meters_per_px_x=abs(self.x1-self.x0)/self.width; meters_per_px_z=abs(self.z1-self.z0)/self.height
        px_area_to_m2=meters_per_px_x*meters_per_px_z
        detected=[]
        gray=cv2.cvtColor(self.img,cv2.COLOR_BGR2GRAY)
        for y in range(0,self.height-patch_size,stride):
            for x in range(0,self.width-patch_size,stride):
                patch=gray[y:y+patch_size,x:x+patch_size]
                filtered=cv2.bilateralFilter(patch,5,50,50)
                edges=cv2.Canny(filtered,40,120)
                kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(3,3))
                closed=cv2.morphologyEx(edges,cv2.MORPH_CLOSE,kernel,iterations=2)
                contours,_=cv2.findContours(closed,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                for cnt in contours:
                    area_px=cv2.contourArea(cnt); area_m2=area_px*px_area_to_m2
                    if min_area_m2<=area_m2<=max_area_m2:
                        rect=cv2.minAreaRect(cnt); (rcx,rcy),(rw,rh),angle=rect
                        rect_area_px=max(1.0,rw*rh); solidity=area_px/rect_area_px
                        if solidity<0.70: continue
                        aspect=max(rw,rh)/max(1.0,min(rw,rh))
                        if aspect>3.2: continue
                        box_pts=cv2.boxPoints(rect)
                        global_pts=[(pt[0]+x,pt[1]+y) for pt in box_pts]
                        metric_pts=[self.pixel_to_meters(gpt[0],gpt[1]) for gpt in global_pts]
                        roof_color=self.sample_roof_color(metric_pts); r,g,b=roof_color
                        if g>r*1.15 and g>b: continue
                        if r<0.28 and g<0.28 and b<0.28: continue
                        detected.append({"polygon":metric_pts,"area_m2":area_m2,"roof_color":roof_color,"height":3.8+min(12.0,area_m2*0.015)})
        print(f"[OpenCV] Detección por parches completada: {len(detected)} estructuras válidas reconocidas.")
        return detected

    def detect_vegetation_patches(self,patch_size=128,stride=96,min_area_m2=2.0,max_area_m2=35.0,max_trees=600):
        """FASE 2b: umbral más bajo para beige Aguascalientes"""
        if self.img is None: return []
        meters_per_px_x=abs(self.x1-self.x0)/self.width; meters_per_px_z=abs(self.z1-self.z0)/self.height
        px_area_to_m2=meters_per_px_x*meters_per_px_z
        trees=[]
        print(f"[OpenCV FASE2b] Detectando vegetación umbral bajo...")
        hsv=cv2.cvtColor(self.img,cv2.COLOR_BGR2HSV)
        # Más permisivo: 25-90 hue, baja saturación
        lower_green=np.array([25,30,30]); upper_green=np.array([90,255,255])
        green_mask=cv2.inRange(hsv,lower_green,upper_green)
        kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        green_mask=cv2.morphologyEx(green_mask,cv2.MORPH_OPEN,kernel,iterations=2)
        green_mask=cv2.morphologyEx(green_mask,cv2.MORPH_CLOSE,kernel,iterations=2)
        contours,_=cv2.findContours(green_mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area_px=cv2.contourArea(cnt); area_m2=area_px*px_area_to_m2
            if min_area_m2<=area_m2<=max_area_m2:
                M=cv2.moments(cnt)
                if M["m00"]==0: continue
                cx=int(M["m10"]/M["m00"]); cz=int(M["m01"]/M["m00"])
                if not (0<=cx<self.width and 0<=cz<self.height): continue
                mx,mz=self.pixel_to_meters(cx,cz)
                bgr=self.img[cz,cx]; b,g,r=int(bgr[0]),int(bgr[1]),int(bgr[2])
                # Más permisivo: g > r y g > b*0.9
                if g>r-5 and g>b*0.85:
                    radius=max(1.2,min(3.5,math.sqrt(area_m2)*0.55))
                    trees.append({"x":mx,"z":mz,"radius":radius,"area":area_m2})
                    if len(trees)>=max_trees: break
        print(f"[OpenCV FASE2b] Vegetación detectada: {len(trees)} árboles (umbral bajo)")
        return trees

    def detect_zebra_crossing(self,center_meters,road_dir_vec,search_radius_m=8.0):
        if self.img is None: return True
        cx,cz=center_meters; px,py=self.meters_to_pixel(cx,cz)
        meters_per_px=abs(self.x1-self.x0)/self.width; rad_px=int(max(4,search_radius_m/meters_per_px))
        x_start=max(0,px-rad_px); y_start=max(0,py-rad_px); x_end=min(self.width,px+rad_px); y_end=min(self.height,py+rad_px)
        roi=self.img[y_start:y_end,x_start:x_end]
        if roi.size==0: return True
        gray_roi=cv2.cvtColor(roi,cv2.COLOR_BGR2GRAY); white_mask=(gray_roi>190).astype(np.uint8); white_ratio=np.mean(white_mask)
        return 0.05<white_ratio<0.60
