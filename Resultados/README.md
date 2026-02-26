# Sentencias judiciales – RAG con Pinecone y OpenAI

Proyecto para **indexar sentencias judiciales** desde un Excel en una base de datos vectorial (Pinecone) y consultarlas mediante un **agente de IA** (RAG) que responde usando solo ese conocimiento.

## Estructura del proyecto

Desde la **raíz del repositorio**:

```
├── Datos/
│   └── sentencias_pasadas.xlsx   # Fuente de sentencias (columnas: Providencia, sintesis, etc.)
├── Resultados/
│   ├── indexar_sentencias_pinecone.ipynb   # Indexación: Excel → embeddings OpenAI → Pinecone
│   ├── agente_sentencias_rag.ipynb         # Agente: preguntas en lenguaje natural → búsqueda + LLM
│   ├── api_agente_sentencias.py            # API FastAPI para consultas (POST /preguntar)
│   ├── requirements.txt
│   ├── .env.example                        # Plantilla (.env)
│   ├── informe-sentencias-rag.md           # Informe técnico del caso
│   └── README.md
├── venv/                          # Entorno virtual (crear en la raíz; no se sube a Git)
└── .gitignore
```

Los notebooks leen el Excel en `../Datos/sentencias_pasadas.xlsx` y el `.env` en la carpeta **Resultados**.

## Requisitos

- **Python 3.10+**
- **OpenAI API Key** (embeddings `text-embedding-3-small` y chat: **gpt-4.1-mini**)
- **Pinecone API Key** (índice serverless en [app.pinecone.io](https://app.pinecone.io/))

## Instalación

1. **Clonar o descargar** el proyecto y abrir una terminal en la carpeta raíz.

2. **Crear y activar el entorno virtual:**
   ```bash
   python -m venv venv
   ```
   - Windows (PowerShell): `.\venv\Scripts\Activate.ps1`  
     Si falla por política de ejecución: `Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process` y luego activar.
   - Windows (CMD): `venv\Scripts\activate.bat`
   - Linux/macOS: `source venv/bin/activate`

3. **Instalar dependencias** (desde la raíz del proyecto o desde `Resultados/`):
   ```bash
   pip install -r requirements.txt
   ```
   Si `requirements.txt` está en `Resultados/`: `pip install -r Resultados/requirements.txt`

4. **Configurar claves (no subir a Git):**
   - En la carpeta **Resultados**, copiar `.env.example` a `.env`.
   - Editar `Resultados/.env` y rellenar `OPENAI_API_KEY` y `PINECONE_API_KEY`.

## Uso

1. **Indexar sentencias (una vez, o al actualizar el Excel)**  
   Abrir y ejecutar **`Resultados/indexar_sentencias_pinecone.ipynb`** en orden (ejecutar desde la carpeta **Resultados** para que encuentre `.env` y `../Datos/`).  
   - Lee `../Datos/sentencias_pasadas.xlsx`.  
   - Genera embeddings con OpenAI y los sube al índice Pinecone `sentencias-judiciales`.

2. **Consultar con el agente**  
   Abrir y ejecutar **`Resultados/agente_sentencias_rag.ipynb`** en orden (también desde **Resultados**).  
   - Puedes hacer preguntas en lenguaje natural.  
   - Si mencionas una o varias Providencias (ej. **T-388/19**, **A. 271/22**, **SU.174/21**), el agente las recupera por metadatos y responde con esas sentencias. Se admiten formatos con guión y con punto (una o varias letras).  
   - La celda de ejemplos recorre una lista de preguntas de prueba con un `for` y muestra cada respuesta con texto replegado (72 caracteres).  
   - Opcional: usar la celda con bucle `input()` para preguntas libres; escribe `salir` para terminar.

3. **API REST (opcional)**  
   Desde la carpeta **Resultados** (donde está el `.env`), instalar dependencias si falta y ejecutar:
   ```bash
   uvicorn api_agente_sentencias:app --reload --host 0.0.0.0 --port 8000
   ```
   - **GET** `/health` — comprueba estado y conexión.
   - **POST** `/preguntar` — cuerpo JSON: `{"pregunta": "¿De qué trata la sentencia T-388/19?", "top_k": 5}`. Respuesta: `{"respuesta": "..."}`.  
   Documentación interactiva: http://localhost:8000/docs

## Dependencias principales

- **jupyter** – notebooks
- **pandas**, **openpyxl** – lectura del Excel
- **openai** – embeddings y chat
- **pinecone** – base vectorial
- **python-dotenv** – carga de `.env`
- **fastapi**, **uvicorn** – API REST

Ver versiones en `requirements.txt`.
