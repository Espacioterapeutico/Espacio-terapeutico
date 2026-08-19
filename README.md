# 📋 App de Gestión Clínica - Psic. Paulo Mora

Aplicación de escritorio local y segura diseñada para la gestión de historias clínicas, evolución de consultas, control contable multimoneda y sincronización bidireccional con Google Calendar.

---

## 🚀 Cómo Iniciar la Aplicación

Para tu comodidad, la aplicación cuenta con un script automatizado que crea el entorno de ejecución, instala las dependencias y arranca el servidor local:

1. **Haz doble clic en el archivo `run.bat`** en la carpeta raíz.
2. Espera a que termine de configurar el entorno virtual e instalar las librerías la primera vez.
3. El programa se abrirá automáticamente en tu navegador web predeterminado en la dirección: **`http://127.0.0.1:5000`**
4. La consola de comandos debe permanecer abierta mientras uses la aplicación. Para cerrarla, presiona `Ctrl + C` en la consola o simplemente ciérrala.

---

## 🔒 Seguridad y Primer Ingreso

- **Datos 100% Locales:** Toda la información de tus pacientes, anotaciones y finanzas se almacena de forma segura en el archivo local `clinica.db`. Ningún dato clínico se sube a servidores externos (excepto la sincronización de agenda a Google Calendar si la habilitas).
- **Creación de Cuenta:** La primera vez que abras la aplicación, el sistema detectará que no hay usuarios y te guiará para **Registrar tu Terapeuta** (creando tu usuario y contraseña única).
- **Bloqueo:** Puedes cerrar tu sesión desde el menú lateral para evitar accesos no autorizados si te alejas de tu computadora.

---

## 📅 Sincronización con Google Calendar

La aplicación funciona por defecto en **Modo Local** (gestiona tu agenda en la base de datos de tu computadora). Si deseas sincronizar tus citas con Google Calendar en tiempo real de forma bidireccional, sigue estos pasos:

### Configuración del archivo `credentials.json`:
1. Ingresa a la consola de desarrolladores de Google: [Google Cloud Console](https://console.cloud.google.com/).
2. Crea un proyecto nuevo (ej. *Mi Consultorio*).
3. Busca en la barra superior **Google Calendar API** y haz clic en **Habilitar**.
4. Ve a la sección **Pantalla de consentimiento de OAuth** (OAuth Consent Screen):
   - Tipo de usuario: **Externo**.
   - Completa el nombre de la app (ej. *Mi Consultorio*) y tu correo.
   - En *Permisos (Scopes)*, añade el permiso: `.../auth/calendar`.
   - En *Usuarios de prueba*, **agrega tu dirección de correo de Google** (el que utilizas para tu agenda).
5. Ve a la pestaña **Credenciales**:
   - Haz clic en **Crear credenciales** -> **ID de cliente de OAuth**.
   - Tipo de aplicación: **Aplicación de escritorio (Desktop App)**.
   - Dale un nombre y haz clic en crear.
6. En la lista de credenciales, busca la que acabas de crear y haz clic en el botón de **Descargar JSON** (flecha hacia abajo).
7. Mueve el archivo descargado a la carpeta raíz de este programa y renombralo exactamente a: **`credentials.json`**.
8. Abre la app, ve a la sección **Copia & Ajustes**, y haz clic en el botón **Autorizar Cuenta de Google**. Se abrirá una ventana para dar permisos a tu cuenta. ¡Listo!

---

## 📁 Respaldos y Exportación

### Copia de Seguridad
Desde la sección de **Copia & Ajustes**, puedes:
1. **Descargar Respaldo:** Te descargará una copia exacta del archivo `clinica.db`. Se recomienda guardarlo semanalmente en un pendrive o una carpeta en la nube (como Google Drive o Dropbox).
2. **Restaurar Respaldo:** Te permite subir un archivo `.db` anteriormente descargado para recuperar toda tu información clínica en caso de cambiar de PC o pérdida de datos.

### Exportación de Documentos
Al buscar un paciente y abrir su **Ficha Resumen**, tienes dos opciones en la parte inferior:
- **Exportar Word:** Genera un archivo `.docx` profesional, estructurado con tablas, datos personales, antecedentes de salud e historial cronológico de sesiones terapéuticas.
- **Imprimir / PDF:** Abre el diálogo de impresión nativo de tu navegador. La aplicación cuenta con estilos optimizados para ocultar la barra de navegación y botones automáticamente, formateando el expediente clínico en hojas limpias listas para imprimir o "Guardar como PDF".
