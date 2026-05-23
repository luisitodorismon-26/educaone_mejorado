#!/usr/bin/env bash
# build.sh — Script de build para Render.com
# Compila frontend y prepara backend
set -o errexit

echo "=== EducaOne Build ==="

# 1. Instalar dependencias backend
echo "📦 Instalando dependencias Python..."
pip install -r requirements.txt

# 2. Compilar frontend
echo "🔨 Compilando frontend..."
cd ../frontend
npm install
npm run build

# 3. Copiar build a static/
echo "📁 Copiando frontend a static/..."
cd ../backend
rm -rf static
cp -r ../frontend/dist static

echo "✅ Build completo"
