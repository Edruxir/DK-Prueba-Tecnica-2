# Informe técnico: consulta de sentencias judiciales con RAG

---

## Explicación del caso

Se plantea la necesidad de poder **consultar en lenguaje natural** un conjunto de **sentencias judiciales** almacenadas en una hoja de cálculo (Excel). El objetivo es que un usuario pueda hacer preguntas como "¿De qué trata la demanda A. 271/22?" o "¿Existen casos sobre acoso escolar?" y obtener respuestas basadas únicamente en esas sentencias, sin que el sistema invente información.

El caso se aborda como un problema de **búsqueda semántica** y **generación de respuestas**: hay que localizar los fragmentos relevantes entre muchas sentencias y, a partir de ellos, producir una respuesta clara y fundamentada.

---

## Supuestos

- **Fuente de datos:** Las sentencias se encuentran en un archivo Excel (`sentencias_pasadas.xlsx`) con columnas como Providencia, Relevancia, Fecha Sentencia, Tema - subtema, resuelve, sintesis, etc. Las columnas pueden tener valores faltantes.
- **Identificadores:** Las sentencias se referencian por **Providencia** en formatos como `T-388/19` (con guión), `A. 271/22` (una letra y punto) o `SU.174/21` (varias letras y punto). El mismo formato (o variantes cercanas) puede estar en el Excel y en las consultas de los usuarios.
- **Infraestructura:** Se dispone de API keys de **OpenAI** (para embeddings y modelo de lenguaje) y de **Pinecone** (base de datos vectorial en la nube).
- **Alcance:** La solución se limita a las sentencias indexadas; no se integra con fuentes externas ni con bases de datos jurídicas adicionales. Las respuestas deben apoyarse solo en el contexto recuperado.
- **Uso:** Los usuarios son técnicos o jurídicos que ejecutan notebooks en un entorno local (Python, Jupyter) con las credenciales en un archivo `.env` no versionado.

---

## Formas para resolver el caso y la opción tomada en esta prueba

**Opciones posibles:**

1. **Búsqueda por palabras clave (SQL/Like o filtros en Excel):** Rápida de implementar, pero no captura el significado ("acoso escolar" vs "matoneo"). No escala bien para preguntas en lenguaje natural.
2. **Modelo de lenguaje sin recuperación (solo LLM):** El modelo podría "recordar" casos de forma genérica, con riesgo alto de alucinaciones y sin garantía de ceñirse a las sentencias del Excel.
3. **RAG (Retrieval-Augmented Generation):** Se indexan los textos en una base vectorial; ante cada pregunta se recuperan los fragmentos más similares y se pasan al LLM como contexto. El modelo responde solo con esa información, reduciendo invenciones y permitiendo citar Providencias concretas.
4. **Grafo de conocimiento o ontología jurídica:** Muy potente para relaciones entre sentencias y conceptos, pero requiere más diseño de esquema y tiempo de desarrollo.

**Opción tomada en esta prueba:** **RAG con Pinecone y OpenAI.**

- **Indexación:** El Excel se lee con pandas; se construye un texto por sentencia a partir de sintesis, Resuelve y Tema - subtema (manejo de celdas vacías). Ese texto se convierte en vector con el modelo **text-embedding-3-small** de OpenAI y se sube a un índice **Pinecone** (serverless, métrica coseno), junto con metadatos (Providencia, Fecha, tipo, etc.) para filtrado.
- **Consulta:** El usuario formula una pregunta; se obtiene el embedding de la pregunta y se buscan en Pinecone las sentencias más similares. Si en la pregunta se detectan una o varias Providencias (p. ej. A. 271/22, T-388/19, SU.174/21), se usa **filtro por metadatos** (`$eq` o `$in`) para recuperar esas sentencias de forma directa y no depender solo de la similitud del vector. Se admiten formatos con guión (T-388/19) y con punto con una o varias letras (A. 271/22, SU.174/21).
- **Respuesta:** El contexto recuperado (síntesis, tema, resuelve, Providencia, fecha) se inyecta en un prompt para un modelo de chat (**gpt-4.1-mini**), con instrucciones de responder solo a partir de ese contexto y sin inventar datos.

Esta opción equilibra implementación rápida, escalabilidad (Pinecone) y control sobre la fuente de verdad (solo las sentencias indexadas).

---

## Resultados del análisis de los datos y los modelos

- **Datos:** Se validó la carga del Excel (columnas como Providencia, sintesis, resuelve, Tema - subtema). Se eliminaron columnas totalmente vacías y se filtraron filas sin texto para embedding. Los metadatos se normalizaron a tipos serializables (evitando `numpy.float64` u otros tipos no compatibles con la API de Pinecone).
- **Indexación:** La indexación en Pinecone se realizó por lotes (embeddings por lotes de 100; upsert por lotes de 100). El índice utilizado es **sentencias-judiciales** (dimensión 1536, métrica coseno). Se comprobó que sentencias concretas (p. ej. T-388/19) quedan correctamente almacenadas con su Providencia en metadatos.
- **Recuperación:** Inicialmente las consultas por Providencia concreta (p. ej. "información sobre T-388/19") no devolvían la sentencia porque el embedding se construía solo con síntesis/tema/resuelve y no con el código. Se incorporó:
  - Detección de **todas** las Providencias en la pregunta (formatos con guión: T-388/19; con punto y una o varias letras: A. 271/22, SU.174/21).
  - Uso de **fetch_by_metadata** (y filtro `$in` para varias Providencias) para recuperar por metadatos.
  - Variantes de formato (espacios, punto con/sin espacio) para mayor robustez frente a diferencias entre Excel y redacción del usuario.
  Con estos cambios, las consultas por una o varias Providencias (p. ej. A. 271/22, SU.174/21, T-388/19) recuperan las sentencias correctas cuando el valor en la BD coincide con alguna variante probada.
- **Modelos:** **text-embedding-3-small** (1536 dimensiones) para embeddings; modelo de chat **gpt-4.1-mini** para la respuesta. La temperatura se mantuvo baja (0,3) para respuestas más estables y ancladas al contexto.
- **Ejemplos de uso:** Se definieron seis ejemplos de consultas (por sentencia y "de qué tratan") para tres casos (tres demandas, acoso escolar, PIAR). La celda de ejemplo recorre **todos** los elementos de la lista con un `for` y muestra cada respuesta con texto replegado a 72 caracteres para facilitar la lectura. Opcional: bucle interactivo con `input()` para preguntas libres (escribir `salir` para terminar).

En conjunto, el flujo RAG (indexación + recuperación por similitud y por Providencia + generación con contexto) cumple el objetivo de responder en lenguaje natural apoyándose solo en las sentencias del Excel.

---

## Futuros ajustes o mejoras

- **Formato de Providencia en BD:** Si en el Excel aparecen más variantes (p. ej. "A-271/22", "271/22", otras abreviaturas con punto), ampliar en `agente_sentencias_rag.ipynb` los patrones regex (`PATRON_CON_GUION`, `PATRON_CON_PUNTO`) y la lista de variantes en `_variantes_valor` / `_fetch_por_providencias` para evitar fallos de coincidencia.
- **Inclusión de Providencia en el embedding:** Añadir la columna Providencia al texto que se embede en el notebook de indexación, de modo que la búsqueda semántica también refuerce la recuperación cuando el usuario menciona un código (y reindexar).
- **Filtros adicionales:** Permitir filtrar por rango de fechas, tema o tipo de sentencia en la consulta (usando metadatos en Pinecone) para acotar el contexto antes de llamar al LLM.
- **Chunking:** Si las sentencias son muy largas, dividir síntesis o "resuelve" en fragmentos más pequeños y indexar cada chunk con referencia a la Providencia, mejorando la precisión de la recuperación para preguntas muy concretas.
- **Evaluación:** Definir un conjunto de preguntas de prueba y métricas (recall de Providencias relevantes, satisfacción, ausencia de alucinaciones) para comparar cambios de modelo, de `top_k` o de prompt.
- **Interfaz:** Sustituir o complementar el bucle por consola con una interfaz web (Streamlit, Gradio) o una API REST para uso por no técnicos.
- **Coste y latencia:** Revisar uso de tokens (embedding + chat) y tamaño del contexto inyectado; valorar modelos más baratos o índices con embedding integrado si el volumen crece.
- **Seguridad y auditoría:** Mantener las API keys en `.env` y fuera de control de versiones; documentar versiones de modelos y de índice para reproducibilidad y auditoría.

---

## Apreciaciones y comentarios del caso

Desde una perspectiva de uso por parte de abogados o equipos jurídicos, cabe señalar que la solución actual se apoya **únicamente en jurisprudencia** (las sentencias del Excel). En la práctica, el análisis de un caso suele requerir cruzar esa jurisprudencia con **normativa vigente** (leyes, decretos, resoluciones, circulares) y, en su caso, con doctrina o documentos internos.

Por ello, los abogados podrían plantearse **cargar más fuentes para el contexto**, en especial **normativas**, para complementar la jurisprudencia ya incluida. Así, el agente RAG podría recuperar no solo sentencias relevantes sino también artículos de ley o disposiciones aplicables, ofreciendo respuestas más completas y útiles para la fundamentación de escritos o dictámenes. Esta ampliación implicaría indexar en Pinecone (o en un índice adicional) textos normativos con metadatos adecuados (tipo de norma, número, fecha, materia) y adaptar el flujo de consulta para combinar o priorizar fuentes según el tipo de pregunta.
