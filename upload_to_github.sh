#!/bin/bash
# Script para subir el repositorio a GitHub

echo "======================================"
echo "Instrucciones para subir a GitHub"
echo "======================================"
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Paso 1: Crear repositorio en GitHub${NC}"
echo "---------------------------------------"
echo "1. Visita: https://github.com/new"
echo "2. Repository name: whatsapp_waha"
echo "3. Description: WAHA Integration for Odoo v18 - WhatsApp messaging module"
echo "4. Visibilidad: Elige Public o Private"
echo "5. NO selecciones ninguna opción de inicialización (README, .gitignore, license)"
echo "6. Haz clic en 'Create repository'"
echo ""

echo -e "${YELLOW}Paso 2: Conectar repositorio local con GitHub${NC}"
echo "---------------------------------------"
echo "Después de crear el repositorio en GitHub, ejecuta:"
echo ""
echo -e "${GREEN}git remote add origin https://github.com/pedrojabie/whatsapp_waha.git${NC}"
echo ""
echo "O si usas SSH:"
echo -e "${GREEN}git remote add origin git@github.com:pedrojabie/whatsapp_waha.git${NC}"
echo ""

echo -e "${YELLOW}Paso 3: Subir el código${NC}"
echo "---------------------------------------"
echo -e "${GREEN}git branch -M main${NC}"
echo -e "${GREEN}git push -u origin main${NC}"
echo ""

echo -e "${YELLOW}Información del commit actual:${NC}"
echo "---------------------------------------"
git log --oneline -1
echo ""
echo "Total de archivos: $(git ls-files | wc -l)"
echo ""

echo -e "${YELLOW}Archivos excluidos (.gitignore):${NC}"
echo "---------------------------------------"
echo "- whatsapp/ (carpeta de referencia de Odoo)"
echo "- __pycache__/"
echo "- *.pyc, *.log"
echo ""

echo "======================================"
echo "¿Todo listo?"
echo "======================================"
echo ""

# Si se pasa el argumento 'execute', ejecutar los comandos
if [ "$1" = "execute" ]; then
    echo -e "${GREEN}Ejecutando comandos...${NC}"
    echo ""
    
    # Verificar si ya existe el remote
    if git remote | grep -q origin; then
        echo "Remote 'origin' ya existe. Verificando URL..."
        git remote -v
    else
        echo "Ingresa la URL de tu repositorio de GitHub:"
        echo "(Ejemplo: https://github.com/pedrojabie/whatsapp_waha.git)"
        read -p "URL: " REPO_URL
        
        if [ -n "$REPO_URL" ]; then
            git remote add origin "$REPO_URL"
            echo -e "${GREEN}✓ Remote agregado${NC}"
        else
            echo "Error: URL vacía"
            exit 1
        fi
    fi
    
    # Cambiar a main
    echo ""
    echo "Cambiando rama a 'main'..."
    git branch -M main
    echo -e "${GREEN}✓ Rama cambiada a main${NC}"
    
    # Push
    echo ""
    echo "Subiendo código a GitHub..."
    git push -u origin main
    
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}======================================"
        echo "✓ ¡Código subido exitosamente!"
        echo "======================================${NC}"
        echo ""
        echo "Tu repositorio está disponible en GitHub"
    else
        echo ""
        echo "Error al subir el código. Verifica:"
        echo "1. Que el repositorio existe en GitHub"
        echo "2. Que tienes permisos de escritura"
        echo "3. Tu autenticación de GitHub"
    fi
else
    echo "Si ya creaste el repositorio en GitHub, ejecuta:"
    echo ""
    echo "  ./upload_to_github.sh execute"
    echo ""
fi
