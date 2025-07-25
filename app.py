from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import openai
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configura la API key de OpenAI desde .env
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@app.route("/webhook", methods=["POST"])
def whatsapp_reply():
    incoming_msg = request.values.get("Body", "").strip()
    
    # Llamar a GPT
    response = client.chat.completions.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": incoming_msg}]
)
    reply = response.choices[0].message.content

    # Responder por WhatsApp
    twilio_response = MessagingResponse()
    msg = twilio_response.message()
    msg.body(reply)

    return str(twilio_response)

if __name__ == "__main__":
    app.run()
    