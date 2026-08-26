import io
import ssl
import threading
import cv2
import numpy as np
import pandas as pd
from PIL import Image
import qrcode
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import requests
import streamlit as st

# Configuración HTTPS para redes corporativas
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# ==========================================
# CONFIGURACIÓN GLOBAL
# ==========================================
URL_API = "https://script.google.com/macros/s/AKfycbzP3t8MMvpm1e4ak3Jr-xeSukifQocpoMHi2Of8Tppqb-8a0CIFzfmvYXl-wqs3RgQM/exec"


def request_api_async(payload):
    """Envía peticiones POST en segundo plano para no congelar la pantalla del celular."""

    def worker():
        try:
            requests.post(URL_API, json=payload, allow_redirects=True)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def request_api(payload):
    """Envía peticiones POST síncronas cuando se requiere respuesta inmediata."""
    try:
        res = requests.post(URL_API, json=payload, allow_redirects=True)
        return res.json()
    except Exception as e:
        return {"exito": False, "error": str(e)}


def fetch_sheet(pestana):
    """Obtiene datos de una pestaña mediante GET."""
    try:
        res = requests.get(f"{URL_API}?pestana={pestana}")
        if res.status_code == 200:
            datos = res.json()
            if isinstance(datos, list) and len(datos) > 0:
                return pd.DataFrame(datos)
    except Exception:
        pass
    return pd.DataFrame()


def decodificar_qr_camara(img_file):
    """Procesa la imagen tomada por la cámara e intenta extraer el texto del QR."""
    if img_file is not None:
        file_bytes = np.asarray(bytearray(img_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if data:
            return data.strip()
    return None


def generar_pdf_etiqueta_bytes(
    id_rollo, ancho, ancho_real, espesor, inspeccion
):
    """Genera la etiqueta en PDF (10 cm x 20 cm) codificando SOLO el ID_Rollo en el QR para lectura ultrarrápida."""
    buffer = io.BytesIO()
    ancho_pdf, largo_pdf = 10 * cm, 20 * cm

    # QR codifica únicamente el ID único (evita saturación y facilita escaneo)
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(id_rollo)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white")

    qr_buffer = io.BytesIO()
    img_qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    c = canvas.Canvas(buffer, pagesize=(ancho_pdf, largo_pdf))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(ancho_pdf / 2, largo_pdf - 1.2 * cm, "MMPM - SLITTER 1")
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(
        ancho_pdf / 2, largo_pdf - 1.8 * cm, "ETIQUETA DE ROLLO DESEMPACADO"
    )
    c.line(
        0.5 * cm, largo_pdf - 2.1 * cm, ancho_pdf - 0.5 * cm, largo_pdf - 2.1 * cm
    )

    c.setFont("Helvetica-Bold", 11)
    y = largo_pdf - 3.2 * cm
    datos = [
        f"ID ROLLO: {id_rollo}",
        f"ANCHO TEÓRICO: {ancho} mm",
        f"ANCHO REAL: {ancho_real} mm",
        f"ESPESOR: {espesor} mm",
        f"INSPECCIÓN: {inspeccion}",
    ]

    for linea in datos:
        c.drawString(0.8 * cm, y, linea)
        y -= 0.85 * cm

    qr_img_reader = ImageReader(qr_buffer)
    c.drawImage(
        qr_img_reader,
        (ancho_pdf - 6.5 * cm) / 2,
        1.2 * cm,
        width=6.5 * cm,
        height=6.5 * cm,
    )

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


# ==========================================
# INICIALIZACIÓN DE ESTADO (SESSION STATE)
# ==========================================
if "usuario_fullname" not in st.session_state:
    st.session_state["usuario_fullname"] = None
if "usuario_nomina" not in st.session_state:
    st.session_state["usuario_nomina"] = None
if "rol" not in st.session_state:
    st.session_state["rol"] = None
if "pantalla_actual" not in st.session_state:
    st.session_state["pantalla_actual"] = "login"
if "paso_verif" not in st.session_state:
    st.session_state["paso_verif"] = 1
if "datos_verif" not in st.session_state:
    st.session_state["datos_verif"] = {
        "ancho_real": 0.0,
        "code_molino": "",
        "code_mmpm": "",
        "code_job": "",
    }

st.set_page_config(
    page_title="Entrada de Rollos a Slitter", layout="centered"
)

# ==========================================
# 1. PANTALLA DE ACCESO (MÓVIL)
# ==========================================
if st.session_state["pantalla_actual"] == "login":
    st.markdown(
        "<h1 style='text-align: center;'>🔒 Entrada de Rollos a Slitter</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align: center; color: gray;'>Ingresa tus datos para acceder al sistema:</p>",
        unsafe_allow_html=True,
    )

    with st.form("form_acceso_movil"):
        nombre = st.text_input("Nombre(s)", placeholder="Ej. Edgar")
        apellido = st.text_input("Apellido(s)", placeholder="Ej. Martinez")
        nomina = st.text_input("Número de Nómina", placeholder="Ej. 56")

        btn_ingresar = st.form_submit_button(
            "Ingresar", use_container_width=True
        )

        if btn_ingresar:
            if not nombre or not apellido or not nomina:
                st.warning(
                    "⚠️ Por favor completa todos los campos para ingresar."
                )
            else:
                res = request_api({
                    "accion": "login",
                    "Nombre": nombre.strip(),
                    "Apellido": apellido.strip(),
                    "Nomina": nomina.strip(),
                })

                if res.get("exito"):
                    st.session_state["usuario_fullname"] = res.get(
                        "NombreCompleto"
                    )
                    st.session_state["usuario_nomina"] = res.get("Nomina")
                    st.session_state["rol"] = res.get("Rol")
                    st.session_state["pantalla_actual"] = "menu_principal"
                    st.rerun()
                else:
                    st.error(
                        f"❌ {res.get('error', 'Nombre, Apellido o Nómina no válidos.')}"
                    )

# ==========================================
# 2. PANTALLA INICIAL (MENÚ DE OPCIONES)
# ==========================================
elif st.session_state["pantalla_actual"] == "menu_principal":
    st.markdown(f"### 👋 Hola {st.session_state['usuario_fullname']}")
    st.caption(
        f"Nómina: {st.session_state['usuario_nomina']} | Rol: {st.session_state['rol']}"
    )
    st.divider()

    st.subheader("Selecciona la operación:")

    if st.button(
        "🔍 Verificación Inicial", use_container_width=True, type="primary"
    ):
        st.session_state["paso_verif"] = 1
        st.session_state["datos_verif"] = {
            "ancho_real": 0.0,
            "code_molino": "",
            "code_mmpm": "",
            "code_job": "",
        }
        st.session_state["pantalla_actual"] = "verificacion_pasos"
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("⚙️ Entrada de Rollo a Línea", use_container_width=True):
        st.session_state["pantalla_actual"] = "ingreso_linea"
        st.rerun()

    if st.session_state["rol"] == "Admin":
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🛠️ Panel de Administración", use_container_width=True):
            st.session_state["pantalla_actual"] = "panel_admin"
            st.rerun()

    st.divider()
    if st.button("🚪 Salir de la Cuenta", use_container_width=True):
        st.session_state["pantalla_actual"] = "login"
        st.session_state["usuario_fullname"] = None
        st.session_state["rol"] = None
        st.rerun()

# ==========================================
# 3. INTERFAZ DE VERIFICACIÓN INICIAL (PASO A PASO)
# ==========================================
elif st.session_state["pantalla_actual"] == "verificacion_pasos":
    paso = st.session_state["paso_verif"]

    # PASO 1: ANCHO REAL
    if paso == 1:
        st.subheader("Paso 1: Ancho Real del Rollo")
        st.write("Realiza la medición física del rollo e ingresa el dato:")

        ancho_val = st.number_input(
            "📐 Ancho Real (mm)",
            min_value=0.0,
            step=0.5,
            format="%.2f",
            value=st.session_state["datos_verif"]["ancho_real"],
        )

        if st.button("Continuar ➡️", use_container_width=True, type="primary"):
            if ancho_val <= 0:
                st.warning("⚠️ Ingresa un valor válido de ancho real.")
            else:
                st.session_state["datos_verif"]["ancho_real"] = ancho_val
                st.session_state["paso_verif"] = 2
                st.rerun()

    # PASO 2: ETIQUETA MOLINO
    elif paso == 2:
        st.subheader("Paso 2: Captura Etiqueta Molino")
        st.write("Usa la cámara del celular para escanear el código:")

        cam_molino = st.camera_input("Escanear Etiqueta Molino", key="cam_molino")
        code_detectado = decodificar_qr_camara(cam_molino)

        code_input = st.text_input(
            "Código detectado / Entrada Manual:",
            value=code_detectado
            if code_detectado
            else st.session_state["datos_verif"]["code_molino"],
        )

        if st.button("Continuar ➡️", use_container_width=True, type="primary"):
            if not code_input:
                st.warning(
                    "⚠️ Debes capturar o ingresar el código de la Etiqueta Molino."
                )
            else:
                st.session_state["datos_verif"]["code_molino"] = (
                    code_input.strip()
                )
                st.session_state["paso_verif"] = 3
                st.rerun()

    # PASO 3: ETIQUETA MMPM
    elif paso == 3:
        st.subheader("Paso 3: Captura Etiqueta MMPM")
        st.write("Usa la cámara del celular para escanear el código:")

        cam_mmpm = st.camera_input("Escanear Etiqueta MMPM", key="cam_mmpm")
        code_detectado = decodificar_qr_camara(cam_mmpm)

        code_input = st.text_input(
            "Código detectado / Entrada Manual:",
            value=code_detectado
            if code_detectado
            else st.session_state["datos_verif"]["code_mmpm"],
        )

        if st.button("Continuar ➡️", use_container_width=True, type="primary"):
            if not code_input:
                st.warning(
                    "⚠️ Debes capturar o ingresar el código de la Etiqueta MMPM."
                )
            else:
                st.session_state["datos_verif"]["code_mmpm"] = code_input.strip()
                st.session_state["paso_verif"] = 4
                st.rerun()

    # PASO 4: JOB WORK ORDER
    elif paso == 4:
        st.subheader("Paso 4: Captura Job Work Order")
        st.write("Usa la cámara para escanear la orden de trabajo:")

        cam_job = st.camera_input("Escanear Job Work Order", key="cam_job")
        code_detectado = decodificar_qr_camara(cam_job)

        code_input = st.text_input(
            "Código detectado / Entrada Manual:",
            value=code_detectado
            if code_detectado
            else st.session_state["datos_verif"]["code_job"],
        )

        if st.button(
            "Finalizar Verificación 🏁",
            use_container_width=True,
            type="primary",
        ):
            if not code_input:
                st.warning(
                    "⚠️ Debes capturar o ingresar el código del Job Work Order."
                )
            else:
                st.session_state["datos_verif"]["code_job"] = code_input.strip()
                st.session_state["paso_verif"] = 5
                st.rerun()

    # PASO 5: VALIDACIÓN Y EVALUACIÓN
    elif paso == 5:
        datos = st.session_state["datos_verif"]
        molino_clean = datos["code_molino"].upper()
        mmpm_clean = datos["code_mmpm"].upper()

        if molino_clean == mmpm_clean:
            st.success("✅ **DATOS OK: VERIFICACIÓN CORRECTA**")

            id_rollo = mmpm_clean
            ancho_teorico = "965"
            espesor = "2.00"
            peso = "10,000"
            especificacion = "Estándar Slitter"
            inspeccion = "OK"

            payload = {
                "accion": "registrar_verificacion",
                "ID_Rollo": id_rollo,
                "Ancho_Teorico": ancho_teorico,
                "Ancho_Real": str(datos["ancho_real"]),
                "Espesor": espesor,
                "Peso": peso,
                "Especificacion": especificacion,
                "Inspeccion": inspeccion,
                "Estatus_Verificacion": "DATOS OK",
                "Quien_Desempaco": st.session_state["usuario_fullname"],
            }
            request_api_async(payload)

            st.divider()
            st.subheader("🖨️ Etiqueta de Control Generada")
            pdf_bytes = generar_pdf_etiqueta_bytes(
                id_rollo,
                ancho_teorico,
                datos["ancho_real"],
                espesor,
                inspeccion,
            )

            st.download_button(
                label="📄 Imprimir / Descargar Etiqueta PDF (10x20 cm)",
                data=pdf_bytes,
                file_name=f"Etiqueta_{id_rollo}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary",
            )
        else:
            st.error(
                "⛔ **DATOS NO COINCIDEN, NOTIFICAR A CALIDAD Y AL SUPERIOR DEL ÁREA**"
            )

        st.divider()
        if st.button("🏠 Volver al Menú Principal", use_container_width=True):
            st.session_state["pantalla_actual"] = "menu_principal"
            st.rerun()

# ==========================================
# 4. INTERFAZ DE INGRESO DE ROLLO A LÍNEA
# ==========================================
elif st.session_state["pantalla_actual"] == "ingreso_linea":
    st.subheader("⚙️ Entrada de Rollo a Línea")
    st.write("Escanea el código QR de la etiqueta recién pegada en el rollo:")

    cam_ingreso = st.camera_input(
        "Escanear Código del Rollo (QR)", key="cam_ingreso"
    )
    code_detectado = decodificar_qr_camara(cam_ingreso)

    code_input = st.text_input(
        "Código detectado / Entrada Manual:",
        value=code_detectado if code_detectado else "",
    )

    if st.button(
        "Confirmar Ingreso a Línea", use_container_width=True, type="primary"
    ):
        if not code_input:
            st.warning("⚠️ Captura o ingresa el código del rollo desempacado.")
        else:
            id_clean = code_input.strip().upper()
            res = request_api({
                "accion": "ingreso_linea",
                "ID_Rollo": id_clean,
                "Quien_Ingreso_Linea": st.session_state["usuario_fullname"],
            })

            if res.get("exito"):
                st.success(
                    f"🎉 Rollo **{id_clean}** ingresado a la línea correctamente."
                )
                st.balloons()
            else:
                st.error(
                    f"❌ Error: {res.get('error', 'ID no encontrado en la base de datos.')}"
                )

    st.divider()
    if st.button("🏠 Volver al Menú Principal", use_container_width=True):
        st.session_state["pantalla_actual"] = "menu_principal"
        st.rerun()

# ==========================================
# 5. PANEL DE ADMINISTRACIÓN (SOLO ADMIN)
# ==========================================
elif st.session_state["pantalla_actual"] == "panel_admin":
    st.header("🛠️ Panel Administrador y Monitoreo")

    st.link_button(
        "📊 Abrir Google Sheets Completo",
        "https://docs.google.com/spreadsheets/",
    )
    st.divider()

    tab1, tab2 = st.tabs(["📦 Rollos Registrados", "👥 Gestión de Personal"])

    with tab1:
        st.subheader("Bitácora de Rollos")
        df_rollos = fetch_sheet("Registro_Rollos")
        if not df_rollos.empty:
            st.dataframe(df_rollos, use_container_width=True)
        else:
            st.info("No hay registros disponibles.")

    with tab2:
        st.subheader("Plantilla de Personal Registrada")
        df_users = fetch_sheet("Usuarios")
        if not df_users.empty:
            st.dataframe(df_users, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            with st.form("form_add_user"):
                st.markdown("**Agregar Integrante**")
                u_nom = st.text_input("Nombre(s)")
                u_ape = st.text_input("Apellido(s)")
                u_nomina = st.text_input("Nómina")
                u_rol = st.selectbox("Rol", ["Operario", "Admin"])
                if st.form_submit_button("Crear Cuenta"):
                    res = request_api({
                        "accion": "agregar_usuario",
                        "Nombre": u_nom,
                        "Apellido": u_ape,
                        "Nomina": u_nomina,
                        "Rol": u_rol,
                    })
                    if res.get("exito"):
                        st.success("Usuario agregado.")
                        st.rerun()

        with col_b:
            with st.form("form_del_user"):
                st.markdown("**Eliminar Integrante**")
                u_del_nom = st.text_input("Número de Nómina a eliminar")
                if st.form_submit_button("Eliminar Cuenta"):
                    res = request_api({
                        "accion": "eliminar_usuario",
                        "Nomina": u_del_nom,
                    })
                    if res.get("exito"):
                        st.success("Usuario eliminado.")
                        st.rerun()

    st.divider()
    if st.button("🏠 Volver al Menú Principal", use_container_width=True):
        st.session_state["pantalla_actual"] = "menu_principal"
        st.rerun()
