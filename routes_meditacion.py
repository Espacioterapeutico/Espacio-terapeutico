import os
import uuid
from flask import Blueprint, request, jsonify, render_template, current_app, redirect
from werkzeug.utils import secure_filename
from app import get_db, login_required, get_psicologo_id_filter
from datetime import datetime

meditaciones_bp = Blueprint('meditaciones', __name__)

ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg', 'm4a'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==========================================
# CATÁLOGO DE MEDITACIONES (PSICÓLOGO)
# ==========================================
@meditaciones_bp.route('/api/meditaciones', methods=['GET'])
@login_required
def get_catalogo():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if psic_id:
        cursor.execute("SELECT * FROM cat_meditaciones WHERE psicologo_id = ? ORDER BY fecha_creacion DESC", (psic_id,))
    else:
        cursor.execute("SELECT * FROM cat_meditaciones ORDER BY fecha_creacion DESC")
        
    meditaciones = [dict(row) for row in cursor.fetchall()]
    return jsonify({'meditaciones': meditaciones})

@meditaciones_bp.route('/api/meditaciones', methods=['POST'])
@login_required
def add_catalogo():
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter() or 1
    
    titulo = request.form.get('titulo')
    tipo = request.form.get('tipo') # 'audio' o 'youtube'
    url_youtube = request.form.get('url_youtube')
    
    if not titulo or not tipo:
        return jsonify({'error': 'Faltan campos obligatorios'}), 400
        
    url_contenido = ''
    if tipo == 'youtube':
        if not url_youtube:
            return jsonify({'error': 'Debe proveer el enlace de YouTube'}), 400
        # Parse YouTube URL to standard embed format if possible, otherwise keep as is
        url_contenido = url_youtube
    elif tipo == 'audio':
        if 'audio_file' not in request.files:
            return jsonify({'error': 'No se adjuntó archivo de audio'}), 400
        file = request.files['audio_file']
        if file.filename == '':
            return jsonify({'error': 'No seleccionó ningún archivo'}), 400
        if file and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = f"meditacion_{psic_id}_{uuid.uuid4().hex[:8]}.{ext}"
            
            upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'meditaciones')
            os.makedirs(upload_folder, exist_ok=True)
            
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            url_contenido = f"/static/uploads/meditaciones/{filename}"
        else:
            return jsonify({'error': 'Formato de audio no permitido'}), 400

    cursor.execute("""
        INSERT INTO cat_meditaciones (psicologo_id, titulo, tipo_contenido, url_contenido)
        VALUES (?, ?, ?, ?)
    """, (psic_id, titulo, tipo, url_contenido))
    db.commit()
    
    return jsonify({'message': 'Meditación agregada al catálogo', 'id': cursor.lastrowid})

@meditaciones_bp.route('/api/meditaciones/<int:med_id>', methods=['DELETE'])
@login_required
def delete_catalogo(med_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter()
    
    if psic_id:
        cursor.execute("SELECT url_contenido, tipo_contenido FROM cat_meditaciones WHERE id = ? AND psicologo_id = ?", (med_id, psic_id))
    else:
        cursor.execute("SELECT url_contenido, tipo_contenido FROM cat_meditaciones WHERE id = ?", (med_id,))
        
    row = cursor.fetchone()
    if not row:
        return jsonify({'error': 'Meditación no encontrada'}), 404
        
    # Eliminar asignaciones vinculadas
    cursor.execute("DELETE FROM paciente_meditaciones WHERE meditacion_id = ?", (med_id,))
    
    # Eliminar meditación
    cursor.execute("DELETE FROM cat_meditaciones WHERE id = ?", (med_id,))
    db.commit()
    
    # Intentar borrar archivo físico
    if row['tipo_contenido'] == 'audio' and row['url_contenido'].startswith('/static/uploads/'):
        try:
            filepath = os.path.join(current_app.root_path, row['url_contenido'].lstrip('/'))
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
            
    return jsonify({'message': 'Meditación eliminada'})

# ==========================================
# ASIGNACIÓN A PACIENTES
# ==========================================
@meditaciones_bp.route('/api/pacientes/<int:paciente_id>/meditaciones', methods=['GET'])
@login_required
def get_paciente_meditaciones(paciente_id):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT pm.id as asignacion_id, pm.hora_recordatorio, pm.activa, pm.token_acceso,
               cm.id as meditacion_id, cm.titulo, cm.tipo_contenido, cm.url_contenido
        FROM paciente_meditaciones pm
        JOIN cat_meditaciones cm ON pm.meditacion_id = cm.id
        WHERE pm.paciente_id = ?
    """, (paciente_id,))
    asignaciones = [dict(row) for row in cursor.fetchall()]
    
    # Añadir rachas y completadas hoy
    today_str = datetime.now().strftime("%Y-%m-%d")
    for asig in asignaciones:
        cursor.execute("""
            SELECT completada, animo_antes, animo_despues FROM registro_meditaciones 
            WHERE asignacion_id = ? AND fecha = ?
        """, (asig['asignacion_id'], today_str))
        reg_hoy = cursor.fetchone()
        asig['completada_hoy'] = bool(reg_hoy and reg_hoy['completada'])
        asig['animo_antes'] = reg_hoy['animo_antes'] if reg_hoy else None
        asig['animo_despues'] = reg_hoy['animo_despues'] if reg_hoy else None
        
        # Calcular racha (días consecutivos completados hasta hoy/ayer)
        cursor.execute("""
            SELECT fecha, completada FROM registro_meditaciones
            WHERE asignacion_id = ? AND completada = 1
            ORDER BY fecha DESC LIMIT 30
        """, (asig['asignacion_id'],))
        regs = cursor.fetchall()
        racha = 0
        from datetime import timedelta
        check_dt = datetime.now().date()
        if not asig['completada_hoy']:
            check_dt -= timedelta(days=1)
            
        for r in regs:
            f = datetime.strptime(r['fecha'], "%Y-%m-%d").date()
            if f == check_dt:
                racha += 1
                check_dt -= timedelta(days=1)
            elif f > check_dt:
                pass # Ignorar futuros raros
            else:
                break
        asig['racha'] = racha
        
    return jsonify({'asignaciones': asignaciones})

@meditaciones_bp.route('/api/pacientes/<int:paciente_id>/meditaciones', methods=['POST'])
@login_required
def assign_meditacion(paciente_id):
    db = get_db()
    cursor = db.cursor()
    psic_id = get_psicologo_id_filter() or 1
    
    data = request.json
    meditacion_id = data.get('meditacion_id')
    hora = data.get('hora_recordatorio')
    
    if not meditacion_id or not hora:
        return jsonify({'error': 'Debe seleccionar una meditación y una hora'}), 400
        
    token = str(uuid.uuid4())
    
    cursor.execute("""
        INSERT INTO paciente_meditaciones (paciente_id, psicologo_id, meditacion_id, hora_recordatorio, token_acceso)
        VALUES (?, ?, ?, ?, ?)
    """, (paciente_id, psic_id, meditacion_id, hora, token))
    db.commit()
    
    return jsonify({'message': 'Meditación asignada al paciente'})

@meditaciones_bp.route('/api/pacientes/meditaciones/<int:asignacion_id>', methods=['DELETE'])
@login_required
def unassign_meditacion(asignacion_id):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("DELETE FROM registro_meditaciones WHERE asignacion_id = ?", (asignacion_id,))
    cursor.execute("DELETE FROM paciente_meditaciones WHERE id = ?", (asignacion_id,))
    db.commit()
    
    return jsonify({'message': 'Asignación eliminada'})

# ==========================================
# PORTAL DEL PACIENTE (PÚBLICO CON TOKEN)
# ==========================================
@meditaciones_bp.route('/portal/meditacion/<token>', methods=['GET'])
def portal_meditacion_view(token):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT pm.id as asignacion_id, pm.paciente_id, cm.titulo, cm.tipo_contenido, cm.url_contenido, p.nombres
        FROM paciente_meditaciones pm
        JOIN cat_meditaciones cm ON pm.meditacion_id = cm.id
        JOIN pacientes p ON pm.paciente_id = p.id
        WHERE pm.token_acceso = ? AND pm.activa = 1
    """, (token,))
    
    asig = cursor.fetchone()
    if not asig:
        return "Meditación no encontrada o desactivada.", 404
        
    # Transformar url de youtube si es necesario (para embed)
    url_embed = asig['url_contenido']
    if asig['tipo_contenido'] == 'youtube':
        if 'watch?v=' in url_embed:
            vid = url_embed.split('watch?v=')[1].split('&')[0]
            url_embed = f"https://www.youtube.com/embed/{vid}"
        elif 'youtu.be/' in url_embed:
            vid = url_embed.split('youtu.be/')[1].split('?')[0]
            url_embed = f"https://www.youtube.com/embed/{vid}"
            
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT completada FROM registro_meditaciones WHERE asignacion_id = ? AND fecha = ?", (asig['asignacion_id'], today_str))
    reg = cursor.fetchone()
    completada_hoy = bool(reg and reg['completada'])
    
    # Rachas
    cursor.execute("""
        SELECT fecha, completada FROM registro_meditaciones
        WHERE asignacion_id = ? AND completada = 1
        ORDER BY fecha DESC LIMIT 30
    """, (asig['asignacion_id'],))
    regs = cursor.fetchall()
    racha = 0
    from datetime import timedelta
    check_dt = datetime.now().date()
    if not completada_hoy:
        check_dt -= timedelta(days=1)
        
    for r in regs:
        f = datetime.strptime(r['fecha'], "%Y-%m-%d").date()
        if f == check_dt:
            racha += 1
            check_dt -= timedelta(days=1)
        elif f > check_dt:
            pass 
        else:
            break
            
    return render_template('portal_meditacion.html', 
                           asig=asig, 
                           url_embed=url_embed,
                           completada_hoy=completada_hoy,
                           racha=racha,
                           token=token)

@meditaciones_bp.route('/portal/meditacion/<token>/log', methods=['POST'])
def portal_meditacion_log(token):
    db = get_db()
    cursor = db.cursor()
    
    cursor.execute("""
        SELECT pm.id as asignacion_id, pm.paciente_id
        FROM paciente_meditaciones pm
        WHERE pm.token_acceso = ? AND pm.activa = 1
    """, (token,))
    
    asig = cursor.fetchone()
    if not asig:
        return jsonify({'error': 'Inválido'}), 404
        
    data = request.json
    animo_antes = data.get('animo_antes')
    animo_despues = data.get('animo_despues')
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("SELECT id FROM registro_meditaciones WHERE asignacion_id = ? AND fecha = ?", (asig['asignacion_id'], today_str))
    row = cursor.fetchone()
    if row:
        cursor.execute("""
            UPDATE registro_meditaciones 
            SET completada = 1, animo_antes = ?, animo_despues = ?
            WHERE id = ?
        """, (animo_antes, animo_despues, row['id']))
    else:
        cursor.execute("""
            INSERT INTO registro_meditaciones (asignacion_id, paciente_id, fecha, completada, animo_antes, animo_despues)
            VALUES (?, ?, ?, 1, ?, ?)
        """, (asig['asignacion_id'], asig['paciente_id'], today_str, animo_antes, animo_despues))
        
    db.commit()
    return jsonify({'message': 'Registro guardado'})
