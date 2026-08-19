@echo off
title Mi Consultorio - Iniciando Servidor...
echo ============================================================
echo   Iniciando App de Gestion Clinica - Psic. Paulo Mora
echo ============================================================
echo.

:: Verificar si existe el entorno virtual .venv, si no, crearlo
if not exist .venv (
    echo [INFO] No se encontro el entorno virtual. Creando uno nuevo...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual de Python. Asegurate de tener Python instalado correctamente.
        pause
        exit /b 1
    )
    echo [INFO] Entorno virtual creado con exito.
    echo.
)

:: Activar entorno virtual
echo [INFO] Activando entorno virtual...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)
echo.

:: Instalar dependencias
echo [INFO] Verificando e instalando dependencias (esto puede tomar un minuto)...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Error al instalar dependencias de Python. Verifica tu conexion a internet.
    pause
    exit /b 1
)
echo.

:: Ejecutar la aplicacion
echo [INFO] Servidor listo. Iniciando aplicacion...
echo [INFO] Se abrira tu navegador de forma automatica en: http://127.0.0.1:5000
echo.
python app.py

:: Pausar en caso de que termine o ocurra un error
if errorlevel 1 (
    echo.
    echo [ERROR] El servidor Flask se ha detenido inesperadamente.
    pause
)
