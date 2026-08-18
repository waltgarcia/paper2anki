#!/usr/bin/env python3
"""articulo_anki.py — convierte un artículo (PDF) en 25-30 cartas Anki (Q/A) con DeepSeek.
Uso: /usr/bin/python3 articulo_anki.py articulo.pdf [--n 25] [--out DIR] [--cita "Autor Año, Rev"] [--max-chars 14000]
Salida: <nombre>_<n>cartas.tsv (importable en Anki) + .apkg si genanki está instalado.
"""
import argparse, json, os, re, sys

HOME = os.path.expanduser("~")

def load_key():
    p = os.path.join(HOME, ".hermes/.env")
    if os.path.exists(p):
        for line in open(p):
            m = re.match(r"^DEEPSEEK_API_KEY=(.*)$", line.strip())
            if m:
                return m.group(1).strip()
    return ""

def extract_text(pdf, max_chars):
    pages = []
    try:
        import fitz
        doc = fitz.open(pdf)
        for i in range(min(len(doc), 12)):
            pages.append(doc[i].get_text() or "")
        doc.close()
    except Exception:
        from pypdf import PdfReader
        r = PdfReader(pdf)
        for pg in r.pages[:12]:
            try:
                pages.append(pg.extract_text() or "")
            except Exception:
                pass
    text = "\n".join(pages)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:max_chars]

def guess_title(text):
    """Heurística: primera línea del texto que parece título (25-150 chars, no ruido)."""
    for line in text.splitlines()[:40]:
        line = line.strip()
        if 25 <= len(line) <= 150 and not line.isupper() and not re.search(
                r"©|doi:?\s*10\.|vol\.?\s*\d|no\.?\s*\d|abstract|introduction", line, re.I):
            return line
    return ""

def ask_title(text, key):
    prompt = f"Del siguiente texto, responde SOLO con el título del artículo, en una línea, sin comillas:\n---\n{text[:2000]}\n---"
    raw = deepseek(prompt, key, max_tokens=100).strip()
    return raw.splitlines()[0].strip() if raw else ""

def extract_json(s):
    s = s.strip()
    if "```" in s:
        s = re.sub(r"```(?:json)?", "", s).replace("```", "")
    i, j = s.find("["), s.rfind("]")
    if i != -1 and j > i:
        s = s[i:j+1]
    return json.loads(s)

def deepseek(prompt, key, max_tokens=8000):
    import urllib.request
    body = json.dumps({
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens, "temperature": 0.5,
        "response_format": {"type": "json_object"},
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.load(r)["choices"][0]["message"]["content"]

def _gen_once(text, n, key, citation):
    """Un intento de generar n cartas. Devuelve (titulo, cartas)."""
    prompt = f"""Eres un maestro de repaso médico. Del siguiente artículo (cita: {citation}), genera EXACTAMENTE {n} cartas de estudio tipo Anki (pregunta → respuesta), en español, de alta calidad para un médico.

Devuelve SOLO un JSON válido: un objeto con dos claves — "titulo" (el título del artículo, tal cual aparece en el texto) y "cards" (array de {n} objetos {{"f": "<pregunta>", "b": "<respuesta>"}}). Sin markdown ni texto extra.

Distribución recomendada (ajustada a {n} cartas):
- 10%: objetivo/hipótesis del estudio
- 10%: diseño y metodología (tipo de estudio, seguimiento, instrumentos)
- 15%: población y muestra (n, grupos, criterios)
- 30%: resultados clave CON cifras exactas (valores, IC95%, p, RR/OR si aplica)
- 10%: definiciones/conceptos clave del tema
- 10%: conclusión y mensaje principal
- 8%: limitaciones
- 7%: implicación clínica práctica

Reglas: respuestas concretas y con números cuando existan; frente = pregunta cerrada de una línea; revés = respuesta completa de 2-4 líneas; usa <br> para saltos de línea en el revés; todo en español. JSON válido SIN truncar.

TEXTO DEL ARTÍCULO:
---
{text}
---"""
    raw = deepseek(prompt, key)
    if not raw or not raw.strip():
        raise ValueError("DeepSeek devolvió respuesta vacía")
    d = extract_json(raw)
    if isinstance(d, dict) and isinstance(d.get("cards"), list):
        titulo = str(d.get("titulo") or "").strip()
        cards = d["cards"]
    elif isinstance(d, list):
        titulo = ""
        cards = d
    else:
        raise ValueError("formato de respuesta inesperado")
    out = []
    for c in cards[:n]:
        if isinstance(c, dict) and c.get("f") and c.get("b"):
            out.append({"f": str(c["f"]).strip(), "b": str(c["b"]).strip()})
    if len(out) < max(1, int(n * 0.6)):
        raise ValueError(f"solo {len(out)} cartas válidas")
    return titulo, out

def gen_cards(text, n, key, citation):
    """Genera n cartas; si falla, parte en 2 mitades y une."""
    last_err = None
    for attempt in range(3):
        try:
            return _gen_once(text, n, key, citation)
        except Exception as e:
            last_err = e
            print(f"  ⚠️ intento {attempt+1}/3 falló: {e}", file=sys.stderr)
    print("  ⚠️ falló completo — generando en 2 mitades…", file=sys.stderr)
    h1, h2 = n // 2, n - n // 2
    t1, c1 = _gen_once(text, h1, key, citation)
    t2, c2 = _gen_once(text, h2, key, citation)
    return (t1 or t2), (c1 + c2)[:n]

def tsv_field(s):
    s = s.replace("\t", " ").replace("\r", " ").replace("\n", "<br>")
    return s

def write_tsv(cards, path):
    with open(path, "w", encoding="utf-8") as f:
        for c in cards:
            f.write(f"{tsv_field(c['f'])}\t{tsv_field(c['b'])}\n")

def write_apkg(cards, path, deck_name, citation, tags):
    try:
        import genanki
    except ImportError:
        print("  (genanki no instalado — solo TSV. Instalar: /usr/bin/python3 -m pip install --user genanki)")
        return False
    seed = abs(hash(deck_name)) % (2**31)
    model = genanki.Model(
        seed, "Artículo → Cartas",
        fields=[{"name": "Frontal"}, {"name": "Reverso"}, {"name": "Fuente"}],
        templates=[{
            "name": "Q/A",
            "qfmt": "<div style='font-size:22px;line-height:1.4'>{{Frontal}}</div>",
            "afmt": "{{FrontSide}}<hr id='answer'><div style='font-size:18px;line-height:1.45'>{{Reverso}}</div>"
                    "<div style='color:#888;font-size:12px;margin-top:10px'>{{Fuente}}</div>",
        }])
    deck = genanki.Deck(seed, deck_name)
    for c in cards:
        deck.add_note(genanki.Note(model=model, fields=[c["f"], c["b"], citation], tags=tags))
    genanki.Package(deck).write_to_file(path)
    return True

def main():
    ap = argparse.ArgumentParser(description="Artículo PDF → cartas Anki (Q/A)")
    ap.add_argument("pdf", help="ruta al PDF del artículo")
    ap.add_argument("--n", type=int, default=25, help="número de cartas (default 25, máx 30)")
    ap.add_argument("--out", default=None, help="carpeta de salida (default: junto al PDF)")
    ap.add_argument("--cita", default="", help='cita/fuente para la tarjeta, ej "Yin 2025, Spine J"')
    ap.add_argument("--max-chars", type=int, default=14000, help="máx caracteres del texto (default 14000)")
    args = ap.parse_args()

    if not os.path.exists(args.pdf):
        sys.exit(f"❌ No existe el PDF: {args.pdf}")
    n = min(max(args.n, 1), 30)
    key = load_key()
    if not key:
        sys.exit("❌ No hay DEEPSEEK_API_KEY en ~/.hermes/.env")

    print(f"📄 Leyendo {os.path.basename(args.pdf)} …")
    text = extract_text(args.pdf, args.max_chars)
    if len(text.strip()) < 500:
        sys.exit("❌ El PDF no tiene texto extraíble (¿escaneado? → OCR primero)")

    citation = args.cita or os.path.splitext(os.path.basename(args.pdf))[0]
    print(f"🧠 Generando {n} cartas con DeepSeek…")
    titulo, cards = gen_cards(text, n, key, citation)
    if len(cards) < n * 0.8:
        print(f"⚠️ Solo se obtuvieron {len(cards)} cartas válidas — reintenta con --max-chars más alto")
    cards = cards[:n]
    if not titulo:
        titulo = guess_title(text)
    if not titulo or len(titulo) < 20:
        try:
            titulo = ask_title(text, key)
        except Exception:
            titulo = ""
    if titulo:
        citation = args.cita or titulo
    base = re.sub(r'[/\\:*?"<>|]', "_", (titulo or os.path.splitext(os.path.basename(args.pdf))[0]))[:80]
    out_dir = args.out or os.path.dirname(os.path.abspath(args.pdf))
    os.makedirs(out_dir, exist_ok=True)
    tsv_path = os.path.join(out_dir, f"{base}_{len(cards)}cartas.tsv")
    write_tsv(cards, tsv_path)

    apkg_path = os.path.join(out_dir, f"{base}_{len(cards)}cartas.apkg")
    ok_apkg = write_apkg(cards, apkg_path, f"Artículos::{titulo or base}", citation,
                         ["articulo", re.sub(r"\s+", "_", base[:20])])

    print(f"\n✅ Cartas generadas: {len(cards)}")
    print(f"   TSV : {tsv_path}")
    if ok_apkg:
        print(f"   APKG: {apkg_path}  (doble clic para importar en Anki, o `open \"{apkg_path}\"`)")
    print("\n📋 Vista previa (3 cartas):")
    for c in cards[:3]:
        print(f"   · {c['f'][:70]}")
        print(f"     → {c['b'][:80]}")

if __name__ == "__main__":
    main()
