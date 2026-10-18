# 🚀 DESPACHO JURÍDICO DIGITAL ALBRA — Despliegue Automático

## ¿Cómo funciona?

**Doble clic y anda. Sin terminales. Sin PowerShell. Sin joder.**

### Windows
1. Doble clic en `INICIAR_ALBRA.bat`
2. Espera a que levante (instala todo automáticamente)
3. Se abre el navegador con la API

### Linux/Mac
1. Doble clic en `INICIAR_ALBRA.sh` (o `bash INICIAR_ALBRA.sh`)
2. Espera a que levante
3. Se abre el navegador

## ¿Qué hace automáticamente?

1. ✅ Detecta Python (te dice si falta)
2. ✅ Crea entorno virtual (.venv)
3. ✅ Instala todas las dependencias
4. ✅ Configura secrets de prueba
5. ✅ Inicializa base de datos
6. ✅ Ejecuta diagnóstico del Doctor
7. ✅ Levanta el servidor HTTP
8. ✅ Abre el navegador en http://localhost:8000/docs

## URLs disponibles

| URL | Descripción |
|-----|-------------|
| http://localhost:8000/docs | Swagger UI (probar API) |
| http://localhost:8000/ | Identidad del agente |
| http://localhost:8000/health | Diagnóstico |
| http://localhost:8000/chat | Chat (POST) |

## Credenciales de prueba

- Usuario: `admin`
- Clave: `albra-local-admin-pass-1234`

## Para detener

Cierra la ventana. Listo.

## Producción real

Cambia los secrets antes de producción:
```
set ALBRA_JWT_SECRET=tu-secreto-real-32-chars
set ALBRA_ADMIN_PASSWORD=tu-password-real
```
