from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import pandas as pd
import time
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configura la API key de OpenAI desde .env
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

df = pd.read_excel("espejos.xlsx")
catalogo = "\n".join([f"{row['Modelo']}: ${row['Precio']}" for _, row in df.iterrows()])

@app.route("/", methods=["GET"])
def health():
    # Render hace GET / para healthcheck; devolvé 200
    return "ok", 200

@app.route("/", methods=["POST"])
def root_post():
    # opcional: log para ver que Twilio llega acá
    app.logger.info("POST / recibido; redirigiendo a whatsapp_reply()")
def whatsapp_reply():
    incoming_msg = request.values.get("Body", "").strip()
    
    # Llamar a GPT
    response = client.chat.completions.create(
    model="gpt-4o-mini",
    
    messages=[
        {"role": "system", "content": f"Sos un vendedor de espejos. Catálogo:\n{catalogo}. Respondé con simpatía, claridad y brevedad. No uses más de 3 líneas."},
        {"role": "user", "content": incoming_msg}]
)
    reply = response.choices[0].message.content


    # Responder por WhatsApp
    twilio_response = MessagingResponse()
    msg = twilio_response.message()
    msg.body(reply)

    return str(twilio_response)

if __name__ == "__main__":
    app.run()
    