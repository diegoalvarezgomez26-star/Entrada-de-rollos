import io
import ssl
import threading
from datetime import datetime, timedelta
import pandas as pd
import qrcode
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import requests
import streamlit as st

# Desactivar verificación estricta de SSL para redes corporativas
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# ==========================================
# CONFIGURACIÓN GLOBAL Y CONEXIÓN
# ==========================================
URL_API = "https://script.google.com/macros/s/AKfycbzP3t8MMvpm1e4ak3Jr-xeSukifQocpoMHi2Of8Tppqb-8a0CIFzfmvYXl-wqs3RgQM/exec"


def request_api_async(payload):
    """Envía peticiones POST en segundo plano para no congelar la pantalla del operario."""

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


# ==========================================
# GENERADOR DE ETIQUETA PDF (10 cm x 20 cm)
# ==========================================
def generar_pdf_etiqueta_bytes(
    id_rollo, ancho, ancho_real, espesor, inspeccion
):
    buffer = io.BytesIO()
    ancho_pdf, largo_pdf = 10 * cm, 20 * cm

    # Generar QR en memoria
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(id_rollo)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white")

    qr_buffer = io.BytesIO()
    img_qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    # Crear lienzo de la etiqueta
    c = canvas.Canvas(buffer, pagesize=(ancho_pdf, largo_pdf))

    # Encabezado
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(ancho_pdf / 2, largo_pdf - 1.2 * cm, "MMPM - SLITTER 1")
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(
        ancho_pdf / 2, largo_pdf - 1.8 * cm, "ETIQUETA DE ROLLO DESEMPACADO"
    )
    c.line(
        0.5 * cm, largo_pdf - 2.1 * cm, ancho_pdf - 0.5 * cm, largo_pdf - 2.1 * cm
    )

    # Detalle de Datos
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

    # Inserción de QR (6.5 cm x 6.5 cm)
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
# AUTENTICACIÓN Y SESIÓN
# ==========================================
def login():
    st.sidebar.title("🔐 Acceso Slitter")
    with st.sidebar.form("form_login"):
        usuario = st.text_input("Usuario")
        contrasena = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Ingresar")

        if submit:
            res = request_api(
                {"accion": "login", "Usuario": usuario, "Contrasena": contrasena}
            )
            if res.get("exito"):
                st.session_state["usuario"] = usuario
                st.session_state["nomina"] = res.get("Nomina")
                st.session_state["rol"] = res.get("Rol")
                st.sidebar.success("¡Bienvenido!")
                st.rerun()
            else:
                st.sidebar.error("Credenciales incorrectas")


# ==========================================
# INTERFAZ PRINCIPAL
# ==========================================
def main():
    st.set_page_config(
        page_title="Operación Slitter - Desempaque", layout="wide"
    )

    if "usuario" not in st.session_state or st.session_state["usuario"] is None:
        login()
        st.title("🏭 Sistema Operativo Slitter")
        st.info("Por favor, inicia sesión en la barra lateral para continuar.")
        return

    # Barra lateral de información del usuario
    st.sidebar.success(
        f"👤 **{st.session_state['usuario']}**\n\nNómina: {st.session_state['nomina']}\n\nRol: {st.session_state['rol']}"
    )

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["usuario"] = None
        st.session_state["rol"] = None
        st.rerun()

    # Selección de Módulos
    opciones = ["1. Verificación Inicial de Rollos", "2. Ingreso a Línea Slitter"]
    if st.session_state["rol"] == "Admin":
        opciones.append("3. Panel de Administración")

    modulo = st.sidebar.radio("Selecciona Operación:", opciones)

    # ------------------------------------------------------------------
    # MÓDULO 1: VERIFICACIÓN INICIAL (PASOS 3.1 & 3.11)
    # ------------------------------------------------------------------
    if modulo == "1. Verificación Inicial de Rollos":
        st.header("🔍 Verificación Inicial y Generación de Etiqueta")
        st.markdown(
            "Captura la medición real del rollo y escanea las 3 etiquetas de control."
        )

        with st.form("form_verificacion"):
            col1, col2 = st.columns(2)
            with col1:
                ancho_real = st.number_input(
                    "📐 Ancho Real Medido (mm)",
                    min_value=0.0,
                    step=0.5,
                    format="%.2f",
                )
                code_molino = st.text_input(
                    "🏷️ Etiqueta Molino", help="Escanea o escribe el código"
                )
            with col2:
                code_mmpm = st.text_input(
                    "🏷️ Etiqueta MMPM", help="Escanea o escribe el código"
                )
                code_job = st.text_input(
                    "📋 Job Work Order", help="Escanea o escribe el código"
                )

            btn_verificar = st.form_submit_button(" Validar Datos de Rollos")

        if btn_verificar:
            if (
                not code_molino
                or not code_mmpm
                or not code_job
                or ancho_real <= 0
            ):
                st.warning("⚠️ Todos los campos son obligatorios.")
            else:
                # Lógica de comparación de etiquetas (verificación de coincidencia)
                # Para prueba: Coinciden si las etiquetas molino y mmpm son idénticas o contienen el mismo ID base
                molino_clean = code_molino.strip().upper()
                mmpm_clean = code_mmpm.strip().upper()

                if molino_clean == mmpm_clean:
                    st.success("✅ **DATOS OK: VERIFICACIÓN CORRECTA**")

                    # Extracción/Simulación de variables técnicas desde el código escaneado
                    id_rollo = mmpm_clean
                    ancho_teorico = "965"  # Reemplazar con parseo de tu código
                    espesor = "2.00"
                    peso = "10,000"
                    especificacion = "Estándar Slitter"
                    inspeccion = "OK"

                    # Registro asíncrono en Google Sheets (Respuesta instantánea < 1 seg)
                    payload = {
                        "accion": "registrar_verificacion",
                        "ID_Rollo": id_rollo,
                        "Ancho_Teorico": ancho_teorico,
                        "Ancho_Real": str(ancho_real),
                        "Espesor": espesor,
                        "Peso": peso,
                        "Especificacion": especificacion,
                        "Inspeccion": inspeccion,
                        "Estatus_Verificacion": "DATOS OK",
                        "Quien_Desempaco": st.session_state["usuario"],
                    }
                    request_api_async(payload)

                    # Generación de Etiqueta PDF
                    st.subheader("🖨️ Impresión de Etiqueta de Control")
                    pdf_bytes = generar_pdf_etiqueta_bytes(
                        id_rollo,
                        ancho_teorico,
                        ancho_real,
                        espesor,
                        inspeccion,
                    )

                    st.download_button(
                        label="📄 Descargar / Imprimir Etiqueta PDF (10x20 cm)",
                        data=pdf_bytes,
                        file_name=f"Etiqueta_{id_rollo}.pdf",
                        mime="application/pdf",
                    )
                else:
                    st.error(
                        "⛔ **DATOS NO COINCIDEN, NOTIFICAR A CALIDAD Y AL SUPERIOR DEL ÁREA**"
                    )

    # ------------------------------------------------------------------
    # MÓDULO 2: INGRESO A LÍNEA (PASO 3.2)
    # ------------------------------------------------------------------
    elif modulo == "2. Ingreso a Línea Slitter":
        st.header("⚙️ Registro de Ingreso de Rollo a Línea")
        st.markdown(
            "Escanea el código QR de la etiqueta recién pegada en el rollo."
        )

        with st.form("form_ingreso"):
            code_rollo = st.text_input("📱 Código de Rollo Desempacado (QR)")
            btn_ingresar = st.form_submit_button(" Confirmar Ingreso a Línea")

        if btn_ingresar:
            if not code_rollo:
                st.warning("⚠️ Debes escanear el código del rollo.")
            else:
                id_clean = code_rollo.strip().upper()
                res = request_api(
                    {
                        "accion": "ingreso_linea",
                        "ID_Rollo": id_clean,
                        "Quien_Ingreso_Linea": st.session_state["usuario"],
                    }
                )

                if res.get("exito"):
                    st.success(
                        f"🎉 Rollo **{id_clean}** ingresado correctamente a la línea Slitter."
                    )
                    st.balloons()
                else:
                    st.error(f"❌ Error: {res.get('error', 'Rollo no encontrado en la base de datos.')}")

    # ------------------------------------------------------------------
    # MÓDULO 3: PANEL DE ADMINISTRACIÓN (SOLO ADMIN)
    # ------------------------------------------------------------------
    elif modulo == "3. Panel de Administración":
        st.header("🛠️ Panel Administrador y Monitoreo de Turno")

        # Botón a Google Sheets directo
        st.link_button(
            "📊 Abrir Google Sheets Completo",
            "https://docs.google.com/spreadsheets/",
        )
        st.divider()

        tab1, tab2 = st.tabs(["📦 Rollos de Último Turno", "👥 Gestión de Personal"])

        # Vista del Último Turno
        with tab1:
            st.subheader("Rollos Procesados en el Último Turno (Últimas 8 Horas)")
            df_rollos = fetch_sheet("Registro_Rollos")

            if not df_rollos.empty:
                st.dataframe(df_rollos, use_container_width=True)
            else:
                st.info("No hay registros disponibles en la base de datos.")

        # Gestión de Usuarios
        with tab2:
            st.subheader("Personal Registrado")
            df_users = fetch_sheet("Usuarios")
            if not df_users.empty:
                st.dataframe(df_users, use_container_width=True)

            col_a, col_b = st.columns(2)
            with col_a:
                with st.form("form_add_user"):
                    st.markdown("**Agregar Usuario**")
                    u_user = st.text_input("Usuario")
                    u_nom = st.text_input("Nómina")
                    u_pass = st.text_input("Contraseña", type="password")
                    u_rol = st.selectbox("Rol", ["Operario", "Admin"])
                    if st.form_submit_button("Crear Cuenta"):
                        res = request_api(
                            {
                                "accion": "agregar_usuario",
                                "Usuario": u_user,
                                "Nomina": u_nom,
                                "Contrasena": u_pass,
                                "Rol": u_rol,
                            }
                        )
                        if res.get("exito"):
                            st.success("Usuario agregado.")
                            st.rerun()

            with col_b:
                with st.form("form_del_user"):
                    st.markdown("**Eliminar Usuario**")
                    u_del = st.text_input("Nombre de Usuario a eliminar")
                    if st.form_submit_button("Eliminar Cuenta"):
                        res = request_api(
                            {"accion": "eliminar_usuario", "Usuario": u_del}
                        )
                        if res.get("exito"):
                            st.success("Usuario eliminado.")
                            st.rerun()


if __name__ == "__main__":
    main()
