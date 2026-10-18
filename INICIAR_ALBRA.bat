@echo off
chcp 65001 >nul 2>&1
title DESPACHO JURÍDICO DIGITAL ALBRA - INICIANDO...
color 0B

echo.
echo  =====================================================
echo    DESPACHO JURIDICO DIGITAL ALBRA
echo    Despliegue Automatico - Doble Clic
echo  =====================================================
echo.

:: Detectar donde está este script
cd /d "%~dp0"

:: Verificar si Python existe
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python no encontrado. Descarga de: https://python.org
    echo  Asegurate de marcar "Add Python to PATH" en la instalacion.
    echo.
    pause
    exit /b 1
)

echo  [1/6] Python encontrado:
python --version
echo.

:: Crear venv si no existe
if not exist ".venv" (
    echo  [2/6] Creando entorno virtual...
    python -m venv .venv
    echo  Listo.
) else (
    echo  [2/6] Entorno virtual ya existe.
)
echo.

:: Activar venv
call ".venv\Scripts\activate.bat"

:: Instalar dependencias
echo  [3/6] Instalando dependencias...
pip install -e ".[dev,server]" -q 2>nul
echo  Listo.
echo.

:: Configurar secrets (valores de prueba - cambiar en produccion)
set ALBRA_JWT_SECRET=albra-local-dev-secret-32chars-min
set ALBRA_ADMIN_PASSWORD=albra-local-admin-pass-1234

:: Inicializar base de datos
echo  [4/6] Inicializando almacenamiento...
if not exist "data" mkdir data
echo  Listo.
echo.

:: Ejecutar Doctor (diagnostico)
echo  [5/6] Diagnostico del organismo...
python -m albra.cli doctor 2>nul
echo.

:: Levantar servidor
echo  [6/6] Levantando servidor...
echo.
echo  =====================================================
echo    ALBRA ESTA LISTO!
echo.
echo    API:       http://localhost:8000
echo    Swagger:   http://localhost:8000/docs
echo    Chat:      http://localhost:8000/chat (POST)
echo.
echo    Credenciales de prueba:
echo    Usuario: admin
echo    Clave:   albra-local-admin-pass-1234
echo.
echo    Cierra esta ventana para detener.
echo  =====================================================
echo.

:: Abrir navegador automaticamente
start http://localhost:8000/docs

:: Levantar el servidor (bloquea hasta que cierres)
python -m albra.cli serve

pause
