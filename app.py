# app.py
import os
import logging
from dotenv import load_dotenv
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import pandas as pd

# =========================
# CARGA DE ENTORNO / LOGS
# =========================
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp-bot")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY no está seteada. Configúrala en Render > Environment.")

# =========================
# APP + CLIENTES
# =========================
app = Flask(__name__)
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# CATALOGO (opcional)
# =========================
def cargar_catalogo(path="espejos.xlsx"):
    """
    Intenta leer el Excel y construir un catálogo legible.
    Acepta columnas: Modelo/Precio o modelo/precio.
    """
    try:
        df = pd.read_excel(path)
        # Normalizamos nombres de columnas
        cols = {c.lower(): c for c in df.columns}
        col_modelo = cols.get("modelo")
        col_precio = cols.get("precio")
        if not col_modelo or not col_precio:
            logger.warning("Columnas esperadas 'Modelo/Precio' no encontradas en el Excel.")
            return "Catálogo no disponible por el momento."

        # Armamos catálogo
        lines = []
        for _, row in df.iterrows():
            modelo = str(row[col_modelo]).strip()
            try:
                precio = int(float(row[col_precio]))
            except Exception:
                precio = row[col_precio]
            lines.append(f"{modelo}: ${precio}")
        catalogo = "\n".join(lines) if lines else "Catálogo vacío."
        logger.info("Catálogo cargado correctamente (%d items).", len(lines))
        return catalogo

    except Exception as e:
        logger.exception("Error cargando %s", path)
        return "Catálogo no disponible por el momento."

CATALOGO = cargar_catalogo()  # se carga una vez al inicio

# =========================
# RESPUESTA PRINCIPAL
# =========================
def generar_respuesta_ia(mensaje_usuario: str) -> str:
    """
    Llama a OpenAI con un prompt corto y devuelve texto.
    Tiene timeout y manejo de errores para no romper Twilio.
    """
    base_reply = "¡Hola! ¿Qué modelo te interesa? Puedo ayudarte con precios y opciones."
    if not OPENAI_API_KEY:
        return base_reply

    try:
        completion = client.chat.completions.create(
            model="gpt-5",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sos un vendedor de espejos. Tenés este catálogo:\n"
                        f"{CATALOGO}\n\n"
                        "Reglas: respondé con simpatía, claridad y en no más de 3 líneas. "
                        "Si te piden algo fuera del catálogo, pedí más detalles o derivá a humano."
                    ),
                },
                {"role": "user", "content": mensaje_usuario},
            ],
            timeout=12,  # segundos (evitar timeouts de Twilio)
        )
        texto = completion.choices[0].message.content.strip()
        return texto or base_reply
    except Exception:
        logger.exception("Fallo llamada a OpenAI")
        return base_reply

def responder_twilio(texto: str):
    """
    Envuelve un texto en TwiML. Twilio necesita TwiML válido.
    """
    tw = MessagingResponse()
    tw.message(texto)
    return str(tw)

# =========================
# RUTAS
# =========================
@app.route("/", methods=["GET"])
def health():
    # Render/Load balancer healthcheck
    return "ok", 200

@app.route("/", methods=["POST"])
def root_post():
    # Por si Twilio está configurado a la raíz "/"
    logger.info("POST / recibido desde Twilio (root). Encaminando a whatsapp_reply()")
    return whatsapp_reply()

@app.route("/webhook", methods=["POST"])
def whatsapp_reply():
    # Handler oficial del webhook de Twilio
    incoming_msg = request.values.get("Body", "").strip()
    from_num = request.values.get("From", "")
    logger.info("Mensaje entrante: From=%s Body=%r", from_num, incoming_msg)

    try:
        reply_text = generar_respuesta_ia(incoming_msg)
    except Exception:
        logger.exception("Error general en whatsapp_reply()")
        reply_text = "Estoy con un inconveniente técnico puntual. ¿Podés intentar de nuevo en 1 minuto?"

    return responder_twilio(reply_text)

# =========================
# MAIN (local)
# =========================
if __name__ == "__main__":
    # Para pruebas locales: python app.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

    