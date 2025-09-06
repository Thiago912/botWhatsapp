# app.py (fragmento completo clave)

import os
import logging
import base64
import requests  # <== NUEVO
from dotenv import load_dotenv
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import pandas as pd

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("whatsapp-bot")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-5-mini")  # gpt-5-mini o gpt-4o
TEXT_MODEL = os.getenv("TEXT_MODEL", "gpt-4o-mini")     # solo texto (rápido/barato)

app = Flask(__name__)
client = OpenAI(api_key=OPENAI_API_KEY)

# ---------- util: data URL ----------
def _to_data_url(content_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(content_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"

# ---------- cargar catálogo (igual que antes) ----------
def cargar_catalogo(path="espejos.xlsx"):
    try:
        df = pd.read_excel(path)
        cols = {c.lower(): c for c in df.columns}
        col_modelo = cols.get("modelo")
        col_precio = cols.get("precio")
        if not col_modelo or not col_precio:
            logger.warning("Columnas 'Modelo/Precio' no encontradas.")
            return "Catálogo no disponible por el momento."
        lines = []
        for _, row in df.iterrows():
            modelo = str(row[col_modelo]).strip()
            try:
                precio = int(float(row[col_precio]))
            except Exception:
                precio = row[col_precio]
            lines.append(f"{modelo}: ${precio}")
        return "\n".join(lines) if lines else "Catálogo vacío."
    except Exception:
        logger.exception("Error cargando catálogo")
        return "Catálogo no disponible por el momento."

CATALOGO = cargar_catalogo()

# ---------- IA: texto ----------
def completar_texto(mensaje_usuario: str) -> str:
    base_reply = "¡Hola! ¿Qué modelo te interesa? Puedo ayudarte con precios y opciones."
    if not OPENAI_API_KEY:
        return base_reply
    try:
        resp = client.chat.completions.create(
            model=TEXT_MODEL,  # gpt-4o-mini (texto) u otro
            messages=[
                {"role": "system", "content": (
                    "Sos un vendedor de espejos. Catálogo:\n"
                    f"{CATALOGO}\n\n"
                    "Respondé amable, claro, en no más de 3 líneas."
                )},
                {"role": "user", "content": mensaje_usuario}
            ],
            timeout=12
        )
        out = resp.choices[0].message.content.strip()
        return out or base_reply
    except Exception:
        logger.exception("Fallo completar_texto")
        return base_reply

# ---------- IA: visión ----------
def completar_con_imagen(caption: str, data_urls: list[str]) -> str:
    """
    Envía caption + una o más imágenes al modelo con visión (gpt-4o o gpt-5/5-mini).
    data_urls: lista de data URLs 'data:image/...;base64,...'
    """
    base_reply = "Recibí tu imagen. ¿Qué te gustaría saber o qué modelo buscás?"
    if not OPENAI_API_KEY:
        return base_reply

    # Construimos el contenido multimodal
    content_parts = []
    # texto/caption primero
    user_text = caption.strip() if caption else "Analizá la(s) imagen(es) para recomendar un espejo adecuado."
    content_parts.append({"type": "text", "text": user_text})
    # imágenes
    for du in data_urls:
        content_parts.append({"type": "image_url", "image_url": {"url": du}})

    try:
        resp = client.chat.completions.create(
            model=VISION_MODEL,  # gpt-5-mini (visión) o gpt-4o
            messages=[
                {"role": "system", "content": (
                    "Sos un asesor de espejos. Analizá la(s) imagen(es) y el contexto. "
                    "Usá el catálogo cuando corresponda:\n"
                    f"{CATALOGO}\n\n"
                    "Respondé en no más de 4 líneas, concreto y útil (modelo/tamaño/estilo sugerido)."
                )},
                {"role": "user", "content": content_parts}
            ],
            timeout=15
        )
        out = resp.choices[0].message.content.strip()
        return out or base_reply
    except Exception:
        logger.exception("Fallo completar_con_imagen")
        return base_reply

# ---------- Twilio helper ----------
def responder_twilio(texto: str):
    tw = MessagingResponse()
    tw.message(texto)
    return str(tw)

# ---------- webhook ----------
@app.route("/webhook", methods=["POST"])
def whatsapp_reply():
    body = request.values.get("Body", "")
    from_num = request.values.get("From", "")
    num_media = request.values.get("NumMedia", "0")
    logger.info("Msg From=%s NumMedia=%s Body=%r", from_num, num_media, body)

    try:
        n = int(num_media)
    except ValueError:
        n = 0

    # Si hay imágenes, las bajamos
    images_data_urls = []
    if n > 0:
        for i in range(n):
            media_url = request.values.get(f"MediaUrl{i}")
            mime = request.values.get(f"MediaContentType{i}", "application/octet-stream")
            logger.info("Media %d: url=%s mime=%s", i, media_url, mime)

            if not media_url:
                continue

            # Filtramos solo imágenes
            if not mime.startswith("image/"):
                logger.info("Omitiendo adjunto no-imagen (mime=%s)", mime)
                continue

            try:
                r = requests.get(media_url, timeout=10)
                r.raise_for_status()
                du = _to_data_url(r.content, mime)
                images_data_urls.append(du)
            except Exception:
                logger.exception("No pude descargar la imagen %s", media_url)

    # Si recibimos al menos una imagen compatible → usar visión
    if images_data_urls:
        reply = completar_con_imagen(body, images_data_urls)
    else:
        # Solo texto o adjunto no imagen
        reply = completar_texto(body)

    return responder_twilio(reply)

# rutas / y / (POST) por compatibilidad
@app.route("/", methods=["GET"])
def health():
    return "ok", 200

@app.route("/", methods=["POST"])
def root_post():
    logger.info("POST / (root) → redirigiendo a /webhook")
    return whatsapp_reply()
