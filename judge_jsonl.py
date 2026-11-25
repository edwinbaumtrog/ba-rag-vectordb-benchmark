import json
import os
import time
import re
from pathlib import Path
import requests

BASE_URL = os.environ.get("OPENWEBUI_BASE_URL", "http://localhost:8080")
TOKEN = os.environ["OPENWEBUI_TOKEN"]
JUDGE_MODEL = "gpt-oss:120b"

FOLDERS = ["no_rag"]
INPUT_NAME = "results_80_no_rag.jsonl"
OUTPUT_NAME = "judged_results_80_no_rag.jsonl"

TIMEOUT = 600
RETRIES = 3
DELAY = 0.2

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


def load_done_ids(out_path: Path) -> set[str]:
    done = set()
    if not out_path.exists():
        return done
    with out_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "id" in obj:
                done.add(str(obj["id"]))
    return done


def append_jsonl(path: Path, obj: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False))
        f.write("\n")


def parse_score_and_reason(text: str) -> tuple[int | None, str]:
    text = text.strip()
    # 1) Versuch: JSON direkt
    try:
        obj = json.loads(text)
        score = obj.get("score")
        reason = obj.get("reason", "")
        if isinstance(score, int) and 1 <= score <= 10:
            return score, str(reason)
    except Exception:
        pass

    # 2) Fallback: erste Zahl 1-10
    m = re.search(r"\b(10|[1-9])\b", text)
    score = int(m.group(1)) if m else None
    return score, text[:500]


def judge_one(question: str, reference: str, candidate: str) -> tuple[int | None, str, str]:
    prompt = (
        "Bewerte die Modellantwort im Vergleich zur Referenzantwort für die gegebene Frage.\n"
        "Kriterien: Korrektheit und Vollständigkeit relativ zur Referenz. Halluzinationen/irrelevante Details = Abzug.\n"
        "Skala 1-10:\n"
        "10 = vollständig korrekt & vollständig\n"
        "8-9 = korrekt, kleine Auslassungen\n"
        "6-7 = teils korrekt, wichtige Punkte fehlen\n"
        "4-5 = überwiegend falsch, wenige passende Elemente\n"
        "1-3 = falsch/erfunden\n\n"
        "Gib NUR dieses JSON zurück (keinen Fließtext):\n"
        '{"score": <ganze Zahl 1-10>, "reason": "<kurz auf Deutsch>"}\n\n'
        f"FRAGE:\n{question}\n\n"
        f"REFERENZ (Soll):\n{reference}\n\n"
        f"MODELLANTWORT (Ist):\n{candidate}\n"
    )

    payload = {
        "model": JUDGE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = requests.post(
                f"{BASE_URL}/api/chat/completions",
                headers=headers,
                json=payload,
                timeout=TIMEOUT,
            )
            if resp.status_code in (429, 502, 503, 504):
                last_err = f"HTTP {resp.status_code}: {resp.text[:300]}"
                time.sleep(2 * attempt)
                continue

            if resp.status_code == 400:
                # hilft beim Debuggen massiv
                raise RuntimeError(f"HTTP 400: {resp.text[:600]}")

            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
            score, reason = parse_score_and_reason(raw)
            return score, reason, raw

        except Exception as e:
            last_err = str(e)
            time.sleep(2 * attempt)

    raise RuntimeError(f"Judge request failed after {RETRIES} retries: {last_err}")


def main():
    for folder in FOLDERS:
        in_path = Path(folder) / INPUT_NAME
        out_path = Path(folder) / OUTPUT_NAME

        if not in_path.exists():
            print(f"[SKIP] {in_path} nicht gefunden.")
            continue

        done = load_done_ids(out_path)
        print(f"[FOLDER] {folder}: resume={len(done)}")

        with in_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)

                qid = str(row.get("id", ""))
                if qid and qid in done:
                    continue

                question = (row.get("question") or "").strip()
                reference = (row.get("answer") or "").strip()
                candidate = (row.get("model_answer") or "").strip()

                out_row = dict(row)

                if not candidate:
                    out_row["judge_score"] = None
                    out_row["judge_reason"] = "Keine modell_answer vorhanden."
                    append_jsonl(out_path, out_row)
                    continue

                try:
                    score, reason, raw = judge_one(question, reference, candidate)
                    out_row["judge_score"] = score
                    out_row["judge_reason"] = reason
                    # optional fürs Debugging:
                    out_row["judge_raw"] = raw
                    append_jsonl(out_path, out_row)
                    print(f"[{folder}] {qid}: score={score}")

                except Exception as e:
                    out_row["judge_score"] = None
                    out_row["judge_reason"] = f"ERROR: {e}"
                    append_jsonl(out_path, out_row)
                    print(f"[ERROR] [{folder}] {qid}: {e}")

                if DELAY:
                    time.sleep(DELAY)

    print("[OK] fertig.")


if __name__ == "__main__":
    main()
