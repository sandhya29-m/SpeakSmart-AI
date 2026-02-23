import os
import json
import asyncio
import logging
from typing import Optional

import torch
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from vosk import Model, KaldiRecognizer
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# --------------------------
# Config
# --------------------------
VOSK_MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "vosk-model-small-en-us-0.15")
SAMPLE_RATE = 16000

# Choose a local grammar model (downloaded by transformers once, then cached):
# Good & fairly fast:
GRAMMAR_MODEL_NAME = os.environ.get("GRAMMAR_MODEL", "vennify/t5-base-grammar-correction")
# Very small & fast (lower accuracy): "google/flan-t5-small"

# --------------------------
# App
# --------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for local dev. Lock down in prod.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("speaksmart")

# --------------------------
# Load models once
# --------------------------
if not os.path.isdir(VOSK_MODEL_DIR):
    raise RuntimeError(
        f"Vosk model not found at {VOSK_MODEL_DIR}.\n"
        f"Please download and unzip 'vosk-model-small-en-us-0.15' into backend/models/"
    )

logger.info("Loading Vosk ASR model...")
vosk_model = Model(VOSK_MODEL_DIR)

logger.info(f"Loading grammar model: {GRAMMAR_MODEL_NAME} ...")
tokenizer = AutoTokenizer.from_pretrained(GRAMMAR_MODEL_NAME)
g_model = AutoModelForSeq2SeqLM.from_pretrained(GRAMMAR_MODEL_NAME)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
g_model.to(device)
g_model.eval()
logger.info("Models loaded.")

def correct_grammar(text: str) -> str:
    if not text.strip():
        return ""
    # Different models expect different task prefixes; vennify works with plain text.
    # For flan-t5-small you could do: prompt = f"correct grammar: {text}"
    inputs = tokenizer.encode(text, return_tensors="pt", truncation=True, max_length=128).to(device)
    with torch.no_grad():
        outputs = g_model.generate(
            inputs,
            max_length=128,
            num_beams=4,
            early_stopping=True
        )
    corrected = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return corrected

@app.get("/health")
def health():
    return {"ok": True}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    """
    WebSocket protocol:
    - Client sends raw PCM16 mono @16k chunks as binary frames.
    - Server streams back JSON messages:
      {"type":"partial","text":"..."}
      {"type":"final","text":"...", "corrected":"..."}
    """
    await ws.accept()
    logger.info("WebSocket connected.")
    rec = KaldiRecognizer(vosk_model, SAMPLE_RATE)
    rec.SetWords(True)

    try:
        while True:
            message = await ws.receive()
            if "bytes" in message:
                data = message["bytes"]
                if rec.AcceptWaveform(data):
                    # final result
                    result = json.loads(rec.Result())
                    text = (result.get("text") or "").strip()
                    # run grammar correction only for final chunks to keep latency low
                    corrected = correct_grammar(text) if text else ""
                    await ws.send_text(json.dumps({
                        "type": "final",
                        "text": text,
                        "corrected": corrected
                    }))
                else:
                    # partial hypothesis
                    partial = json.loads(rec.PartialResult()).get("partial", "")
                    await ws.send_text(json.dumps({
                        "type": "partial",
                        "text": partial
                    }))
            else:
                # ignore pings/close frames etc.
                await asyncio.sleep(0.001)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected.")
    except Exception as e:
        logger.exception("WebSocket error: %s", e)
        try:
            await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
        finally:
            await ws.close()
