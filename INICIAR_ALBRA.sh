#!/usr/bin/env bash
# DESPACHO JURÍDICO DIGITAL ALBRA - Despliegue automático
# Doble clic o: bash INICIAR_ALBRA.sh

set -e

echo ""
echo " ====================================================="
echo "   DESPACHO JURIDICO DIGITAL ALBRA"
echo "   Despliegue Automatico - Doble Clic"
echo " ====================================================="
echo ""

# Detectar directorio del script
cd "$(dirname "$0")"

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo " [ERROR] Python 3 no encontrado. Instala: python3"
    exit 1
fi

echo " [1/6] Python encontrado:"
python3 --version
echo ""

# Crear venv si no existe
if [ ! -d ".venv" ]; then
    echo " [2/6] Creando entorno virtual..."
    python3 -m venv .venv
    echo " Listo."
else
    echo " [2/6] Entorno virtual ya existe."
fi
echo ""

# Activar venv
source .venv/bin/activate

# Instalar dependencias
echo " [3/6] Instalando dependencias..."
pip install -e ".[dev,server]" -q 2>/dev/null
echo " Listo."
echo ""

# Configurar secrets
export ALBRA_JWT_SECRET="albra-local-dev-secret-32chars-min"
export ALBRA_ADMIN_PASSWORD="albra-local-admin-pass-1234"

# Inicializar base de datos
echo " [4/6] Inicializando almacenamiento..."
mkdir -p data
echo " Listo."
echo ""

# Diagnóstico
echo " [5/6] Diagnostico del organismo..."
python -m albra.cli doctor 2>/dev/null || true
echo ""

# Levantar servidor
echo " [6/6] Levantando servidor..."
echo ""
echo " ====================================================="
echo "   ALBRA ESTA LISTO!"
echo ""
echo "   API:       http://localhost:8000"
echo "   Swagger:   http://localhost:8000/docs"
echo "   Chat:      http://localhost:8000/chat (POST)"
echo ""
echo "   Credenciales:"
echo "   Usuario: admin"
echo "   Clave:   albra-local-admin-pass-1234"
echo ""
echo "   Ctrl+C para detener."
echo " =====================================================echo ""

# Abrir navegador
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:8000/docs &
elif command -v open &> /dev/null; then
    open http://localhost:8000/docs &
fi

# Levantar servidor
python -m albra.cli serve
