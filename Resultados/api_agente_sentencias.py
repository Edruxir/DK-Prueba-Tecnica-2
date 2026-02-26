"""
API FastAPI para el agente RAG de sentencias judiciales.
Expone un endpoint para consultar en lenguaje natural usando el índice Pinecone y OpenAI.

Uso:
  Desde la carpeta Resultados (donde está .env):
    uvicorn api_agente_sentencias:app --reload --host 0.0.0.0 --port 8000
  O desde la raíz del proyecto:
    uvicorn Resultados.api_agente_sentencias:app --reload --host 0.0.0.0 --port 8000
    (y asegurar que .env esté en Resultados/ o que OPENAI_API_KEY y PINECONE_API_KEY estén en el entorno)
"""

import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI
from pinecone import Pinecone

# Cargar .env desde la carpeta del script (Resultados) o desde la raíz del proyecto
_carpeta_script = Path(__file__).resolve().parent
load_dotenv(_carpeta_script / ".env")
load_dotenv(_carpeta_script.parent / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Falta OPENAI_API_KEY en .env")
if not PINECONE_API_KEY:
    raise ValueError("Falta PINECONE_API_KEY en .env")

INDEX_NAME = "sentencias-judiciales"
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4.1-mini"
TOP_K = 5
SYSTEM_PROMPT = """Eres un asistente experto en jurisprudencia colombiana. Tu única fuente de información es el contexto que se te proporciona (fragmentos de sentencias). Responde de forma clara y concisa basándote únicamente en ese contexto. Si el contexto no contiene información suficiente para responder, dilo explícitamente. No inventes datos ni referencias."""

client_openai = OpenAI(api_key=OPENAI_API_KEY)
pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)

# --- Patrones y funciones del agente RAG (misma lógica que el notebook) ---

PATRON_CON_GUION = re.compile(r"([A-Za-z]+)\s*-\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)
PATRON_CON_PUNTO = re.compile(r"([A-Za-z]+)\.\s*(\d+)\s*/\s*(\d+)", re.IGNORECASE)


def extraer_providencias(texto: str) -> list[str]:
    if not texto or not texto.strip():
        return []
    t = texto.strip()
    out = []
    for m in PATRON_CON_GUION.finditer(t):
        letras, n1, n2 = m.group(1), m.group(2), m.group(3)
        out.append(f"{letras.upper()}-{n1}/{n2}")
    for m in PATRON_CON_PUNTO.finditer(t):
        letras, n1, n2 = m.group(1), m.group(2), m.group(3)
        out.append(f"{letras.upper()}. {n1}/{n2}")
    return list(dict.fromkeys(out))


def _variantes_valor(prov: str) -> list[str]:
    v = [prov, prov.replace("-", "- "), prov.replace("/", " / ")]
    if ". " in prov:
        v.append(prov.replace(". ", "."))
    return list(dict.fromkeys(v))


def _fetch_una_providencia(providencia: str, limit: int) -> list[dict]:
    for valor in _variantes_valor(providencia):
        try:
            resp = index.fetch_by_metadata(filter={"Providencia": {"$eq": valor}}, limit=limit)
        except Exception:
            continue
        if not getattr(resp, "vectors", None):
            continue
        out = [
            {"metadata": getattr(vec, "metadata", None) or {}, "score": None}
            for _id, vec in resp.vectors.items()
        ]
        if out:
            return out[:limit]
    return []


def _fetch_por_providencias(providencias: list[str], limit: int) -> list[dict]:
    valores_in = list(providencias)
    for p in providencias:
        if ". " in p:
            valores_in.append(p.replace(". ", "."))
    valores_in = list(dict.fromkeys(valores_in))
    try:
        resp = index.fetch_by_metadata(filter={"Providencia": {"$in": valores_in}}, limit=limit)
        if getattr(resp, "vectors", None):
            out = [
                {"metadata": getattr(vec, "metadata", None) or {}, "score": None}
                for _id, vec in resp.vectors.items()
            ]
            if out:
                return out[:limit]
    except Exception:
        pass
    vistos = set()
    out = []
    for p in providencias:
        for r in _fetch_una_providencia(p, limit=limit):
            key = (r.get("metadata") or {}).get("Providencia", "") or id(r)
            if key not in vistos:
                vistos.add(key)
                out.append(r)
    return out[:limit]


def buscar_sentencias(pregunta: str, top_k: int = TOP_K) -> list[dict]:
    listas = extraer_providencias(pregunta)
    if listas:
        out = _fetch_por_providencias(listas, limit=max(top_k, len(listas) * 2))
        if out:
            return out
    resp = client_openai.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[pregunta.strip() or " "],
    )
    vector = resp.data[0].embedding
    results = index.query(vector=vector, top_k=top_k * 3, include_metadata=True)
    out = []
    for m in results.matches:
        meta = getattr(m, "metadata", None) or {}
        score = getattr(m, "score", None)
        if listas:
            prov_bd = str(meta.get("Providencia", "")).upper().replace(" ", "").replace(".", "").replace("/", "")
            if not any(
                p.upper().replace(" ", "").replace(".", "").replace("/", "") in prov_bd for p in listas
            ):
                continue
        out.append({"metadata": meta, "score": score})
    return out[:top_k]


def contexto_desde_resultados(resultados: list[dict]) -> str:
    partes = []
    for i, r in enumerate(resultados, 1):
        meta = r.get("metadata") or {}
        prov = meta.get("Providencia", "")
        fecha = meta.get("Fecha Sentencia", "")
        tema = meta.get("Tema - subtema", "")
        resuelve = meta.get("resuelve", "")
        sintesis = meta.get("sintesis", "")
        bloque = f"--- Sentencia {i} (Providencia: {prov}, Fecha: {fecha}) ---\n"
        if tema:
            bloque += f"Tema: {tema}\n"
        if sintesis:
            bloque += f"Síntesis: {sintesis}\n"
        if resuelve:
            bloque += f"Resuelve: {resuelve[:1500]}..." if len(str(resuelve)) > 1500 else f"Resuelve: {resuelve}"
        partes.append(bloque)
    return "\n\n".join(partes) if partes else "(No se encontraron sentencias relevantes.)"


def preguntar(pregunta: str, top_k: int = TOP_K) -> str:
    resultados = buscar_sentencias(pregunta, top_k=top_k)
    contexto = contexto_desde_resultados(resultados)
    user_content = f"Contexto (sentencias recuperadas):\n\n{contexto}\n\n---\n\nPregunta del usuario: {pregunta}"
    resp = client_openai.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content or "(Sin respuesta)"


# --- FastAPI ---

app = FastAPI(
    title="API Agente Sentencias RAG",
    description="Consulta en lenguaje natural sobre sentencias judiciales indexadas en Pinecone.",
    version="1.0.0",
)


class PreguntaBody(BaseModel):
    pregunta: str = Field(..., min_length=1, description="Pregunta en lenguaje natural sobre las sentencias")
    top_k: int = Field(default=5, ge=1, le=20, description="Número máximo de sentencias a usar como contexto")


class RespuestaBody(BaseModel):
    respuesta: str


@app.get("/health")
def health():
    """Comprueba que la API y las credenciales estén disponibles."""
    return {"status": "ok", "index": INDEX_NAME, "chat_model": CHAT_MODEL}


@app.post("/preguntar", response_model=RespuestaBody)
def endpoint_preguntar(body: PreguntaBody):
    """
    Envía una pregunta al agente RAG. Recupera sentencias relevantes desde Pinecone
    y genera una respuesta con OpenAI basada solo en ese contexto.
    """
    try:
        respuesta = preguntar(body.pregunta, top_k=body.top_k)
        return RespuestaBody(respuesta=respuesta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
