# Imagen de PRUEBA para medir la memoria del Registro de Secundaria en Linux.
# Mismas dependencias fijadas que producción (backend/requirements.txt, idéntico
# en main 3a5a96b y en el PR #81 a2bfb45). El código NO va en la imagen: se monta
# en tiempo de ejecución (una versión cada vez).
FROM python:3.13-slim
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
WORKDIR /tmp
