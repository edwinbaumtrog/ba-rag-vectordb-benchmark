import json
import time
from typing import List, Dict, Any, Optional
import requests

OPENWEBUI_BASE_URL = "http://10.26.5.81:8080/api"
TOKEN = "sk-372c8765ca1d49a38a16ced2f35b2ea5"
MODEL_NAME = "gpt-oss:120b"

INPUT_JSONL = "queries_80.jsonl"
OUTPUT_JSONL = "results_80_no_rag.jsonl"

REQUEST_DELAY = 1.0
TIMEOUT_SECONDS = 600
MAX_RETRIES = 3

SYSTEM_PROMPT: Optional[str] = None
SYSTEM_PROMPT = (
     "Du bist ein Assistent der FH Aachen und beantwortest Fragen präzise, "
     "kurz und auf Deutsch (max. 6 Sätze). Nutze nach Möglichkeit nur Informationen, die "
     "aus den hinterlegten FH-Aachen-Dokumenten stammen.")
COLLECTION_ID = "FH Aachen"


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_existing_ids(path: str) -> set[str]:
    """Für Resume: liest OUTPUT_JSONL und merkt sich schon beantwortete IDs."""
    done: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                qid = obj.get("id")
                if qid:
                    done.add(str(qid))
    except FileNotFoundError:
        pass
    return done


def append_jsonl(path: str, row: Dict[str, Any]) -> None:
    """Schreibt zeilenweise (damit nichts verloren geht, falls der Run stoppt)."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False))
        f.write("\n")


def call_openwebui_chat(question: str) -> Dict[str, Any]:
    """
    Call /api/chat/completions and return full JSON response (for debug/usage/id).
    """
    url = OPENWEBUI_BASE_URL.rstrip("/") + "/chat/completions"

    messages = []
    if SYSTEM_PROMPT:
        messages.append({"role": "system", "content": SYSTEM_PROMPT})
    messages.append({"role": "user", "content": question})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "stream": False,
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_SECONDS)

            # Bei transienten Fehlern retry
            if resp.status_code in (429, 502, 503, 504):
                last_err = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
                time.sleep(2 * attempt)
                continue

            if resp.status_code == 400:
                print("400 body:", resp.text)  # <- Open WebUI liefert hier meist den Grund


            resp.raise_for_status()
            return resp.json()

        except requests.RequestException as e:
            last_err = e
            time.sleep(2 * attempt)

    raise RuntimeError(f"Request failed after {MAX_RETRIES} retries: {last_err}") from last_err


def extract_answer(data: Dict[str, Any]) -> str:
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unerwartetes Antwortformat: {data}") from e


def main() -> None:
    questions = load_jsonl(INPUT_JSONL)
    done_ids = load_existing_ids(OUTPUT_JSONL)

    print(f"[INFO] {len(questions)} Fragen geladen.")
    if done_ids:
        print(f"[INFO] Resume aktiv: {len(done_ids)} bereits im Output gefunden, wird übersprungen.")

    total = len(questions)
    for i, q in enumerate(questions, start=1):
        qid = str(q.get("id", f"q_{i:03d}"))
        question_text = (q.get("question") or "").strip()

        if not question_text:
            print(f"[WARN] {qid}: kein 'question'-Text, überspringe.")
            continue

        if qid in done_ids:
            print(f"[SKIP] ({i}/{total}) {qid} bereits vorhanden.")
            continue

        print(f"[INFO] ({i}/{total}) Frage {qid} senden ...")

        out_entry = dict(q)
        try:
            data = call_openwebui_chat(question_text)
            out_entry["model_answer"] = extract_answer(data)

            # Optional: nützlich für spätere Analyse
            out_entry["openwebui_response_id"] = data.get("id")
            out_entry["usage"] = data.get("usage")

        except Exception as e:
            print(f"[ERROR] {qid}: {e}")
            out_entry["model_answer"] = ""
            out_entry["error"] = str(e)

        append_jsonl(OUTPUT_JSONL, out_entry)

        if REQUEST_DELAY > 0:
            time.sleep(REQUEST_DELAY)

    print(f"[OK] Fertig. Ergebnisse stehen in {OUTPUT_JSONL}")


if __name__ == "__main__":
    main()
