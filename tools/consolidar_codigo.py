import os
import time

# Configuración: ¿Qué archivos queremos consolidar?
DIRECTORIOS_PERMITIDOS = ['src', 'include', 'tools', 'shaders']
EXTENSIONES_PERMITIDAS = ['.c', '.h', '.py', '.vert', '.frag', 'Makefile']

def consolidar_proyecto():
    archivo_salida = f"street_vulkan_consolidado_{int(time.time())}.txt"
    
    with open(archivo_salida, 'w', encoding='utf-8') as out_f:
        out_f.write("=== ESTRUCTURA DEL PROYECTO (TREE) ===\n")
        
        # 1. Imprimir la estructura de carpetas (tipo 'tree')
        for root, dirs, files in os.walk('.'):
            # Ignoramos carpetas que no queremos
            dirs[:] = [d for d in dirs if d not in ['.git', 'build', '__pycache__', 'assets', 'models']]
            
            nivel = root.replace('.', '').count(os.sep)
            indentacion = ' ' * 4 * nivel
            out_f.write(f"{indentacion}{os.path.basename(root)}/\n")
            sub_indent = ' ' * 4 * (nivel + 1)
            for f in files:
                out_f.write(f"{sub_indent}{f}\n")
                
        out_f.write("\n=== CONTENIDO DE LOS ARCHIVOS ===\n")
        
        # 2. Leer e imprimir el contenido de cada archivo permitido
        for root, _, files in os.walk('.'):
            # Solo buscamos en los directorios permitidos o en la raíz (para el Makefile)
            partes_ruta = root.split(os.sep)
            if len(partes_ruta) > 1 and partes_ruta[1] not in DIRECTORIOS_PERMITIDOS:
                continue

            for file in files:
                ext = os.path.splitext(file)[1]
                if ext in EXTENSIONES_PERMITIDAS or file == 'Makefile':
                    ruta_completa = os.path.join(root, file)
                    out_f.write(f"\n--- INICIO ARCHIVO: {ruta_completa} ---\n")
                    try:
                        with open(ruta_completa, 'r', encoding='utf-8') as in_f:
                            out_f.write(in_f.read())
                    except Exception as e:
                        out_f.write(f"[Error leyendo el archivo: {e}]\n")
                    out_f.write(f"\n--- FIN ARCHIVO: {ruta_completa} ---\n")

    print(f"✅ ¡Consolidación exitosa! Archivo generado: {archivo_salida}")

if __name__ == "__main__":
    consolidar_proyecto()
