# 🃏 articulo-a-anki — de PDF a cartas Anki

Convierte un artículo científico (PDF) en **25-30 cartas de repaso estilo Anki**
(pregunta → respuesta), en español, con enfoque médico, usando DeepSeek.

Salida: **`.tsv`** (importable directo en Anki) y **`.apkg`** (doble clic)
cuando `genanki` está instalado.

## ✨ Características

- **Extracción de texto**: PyMuPDF (fitz) con fallback a pypdf; primeras ~12 páginas truncadas a 14k caracteres (abstract + intro + métodos + resultados).
- **Cartas con distribución pedagógica** (validada con un médico):

| Tema | % de cartas |
|---|---|
| Objetivo / hipótesis | 10% |
| Diseño y metodología | 10% |
| Población y muestra (n, grupos) | 15% |
| Resultados clave CON cifras (IC95, p, RR/OR) | 30% |
| Definiciones / conceptos clave | 10% |
| Conclusión / mensaje principal | 10% |
| Limitaciones | 8% |
| Implicación clínica | 7% |

- **El mazo se nombra con el título del artículo** (extraído por DeepSeek con
  respaldo heurístico + mini-llamada), y el título también es la fuente de cada carta.
- **Robusto**: 3 reintentos automáticos; si el JSON se trunca, parte la
  generación en 2 mitades y une.
- **Sin dependencias pesadas**: solo `pymupdf` (o `pypdf`) + `genanki` opcional.

## 📦 Requisitos

```bash
# Python 3.9+
python3 -m pip install --user pymupdf genanki   # genanki solo para .apkg
```

Necesitas `DEEPSEEK_API_KEY` en el entorno (o en `~/.hermes/.env`, formato `DEEPSEEK_API_KEY=...`).

## 🚀 Uso

```bash
python3 articulo_anki.py articulo.pdf                 # 25 cartas, salida junto al PDF
python3 articulo_anki.py articulo.pdf --n 30          # hasta 30 cartas
python3 articulo_anki.py articulo.pdf --out ~/Documents/Anki
python3 articulo_anki.py articulo.pdf --cita "Yin 2025, Spine J"
```

### Opciones

| Flag | Default | Descripción |
|---|---|---|
| `--n` | 25 | Número de cartas (máx 30) |
| `--out` | dir del PDF | Carpeta de salida |
| `--cita` | título del artículo | Fuente mostrada en cada carta |
| `--max-chars` | 14000 | Máximo de caracteres del texto enviado al LLM |

## 📤 Salida

- `<Título_artículo>_<n>cartas.tsv` — 2 columnas TAB (Frontal, Reverso).
  Importar en Anki: **Archivo → Importar → Separador de campo: Tab → HTML permitido**.
- `<Título_artículo>_<n>cartas.apkg` — mazo `Artículos::<Título>` con plantilla
  Q/A (frente grande, reverso con fuente pequeña).

## 🧠 Notas técnicas (pitfalls resueltos)

- **DeepSeek JSON mode**: `response_format={"type":"json_object"}` +
  `max_tokens=8000` — sin eso el modelo razonador devuelve contenido vacío o truncado.
- El título puede venir vacío del JSON → fallbacks: heurística de la primera
  línea del texto + mini-llamada DeepSeek pidiendo solo el título.
- `genanki` rechaza tags con espacios → sanitizar con `re.sub(r"\s+", "_", ...)`.
- Nombres de archivo sanitizados: `/ : * ? " < > |` → `_`, máx 80 chars.

## 📄 Licencia

MIT — libre para usar, modificar y compartir.
