#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import random
import zipfile
from pathlib import Path
from collections import defaultdict

SEED = 42
N_SAMPLES = 5

ZIP_PATH = Path("daten.zip")                 # ggf. anpassen
EXTRACT_DIR = Path("daten_extracted")        # wird erzeugt
OUT_DIR = Path("tables")                     # LaTeX-Tabellen hierhin
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Heuristik: mögliche ID-Feldnamen
ID_KEYS = ["id", "qid", "question_id", "questionId", "query_id", "item_id"]

def detect_id_key(obj: dict) -> str:
    for k in ID_KEYS:
        if k in obj:
            return k
    # fallback: wenn nur ein Key aussieht wie ID
    for k in obj.keys():
        if "id" in k.lower():
            return k
    raise KeyError(f"Keine ID-Spalte gefunden. Keys: {list(obj.keys())}")

def find_score(obj: dict):
    # häufige Score/Rating Felder
    for k in ["score", "rating", "quality", "grade", "mean_score"]:
        if k in obj and isinstance(obj[k], (int, float)):
            return obj[k]
    # manchmal nested
    if "judge" in obj and isinstance(obj["judge"], dict):
        for k in ["score", "rating", "quality"]:
            if k in obj["judge"] and isinstance(obj["judge"][k], (int, float)):
                return obj["judge"][k]
    return None

def find_reason(obj: dict):
    # optional: Begründung / feedback
    for k in ["reason", "rationale", "explanation", "feedback", "comment"]:
        if k in obj and isinstance(obj[k], str):
            return obj[k]
    if "judge" in obj and isinstance(obj["judge"], dict):
        for k in ["reason", "rationale", "explanation", "feedback", "comment"]:
            if k in obj["judge"] and isinstance(obj["judge"][k], str):
                return obj["judge"][k]
    return ""

def read_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows

def main():
    # 1) unzip
    if ZIP_PATH.exists():
        EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(ZIP_PATH, "r") as z:
            z.extractall(EXTRACT_DIR)
    else:
        raise FileNotFoundError(f"{ZIP_PATH} nicht gefunden")

    # 2) finde alle judged_results_80.jsonl in Unterordnern
    files = sorted(EXTRACT_DIR.rglob("judged_results_80.jsonl"))
    if not files:
        raise FileNotFoundError("Keine judged_results_80.jsonl gefunden (rekursiv).")

    # 3) lade alle Runs: system_name -> {id -> (score, reason)}
    runs = {}
    id_sets = []
    for fp in files:
        system_name = fp.parent.name  # Ordnername als Label
        data = read_jsonl(fp)
        if not data:
            continue

        id_key = detect_id_key(data[0])
        per_id = {}
        for obj in data:
            qid = str(obj.get(id_key))
            score = find_score(obj)
            reason = find_reason(obj)
            per_id[qid] = (score, reason)

        runs[system_name] = per_id
        id_sets.append(set(per_id.keys()))

    # 4) Schnittmenge (nur IDs, die in allen Runs vorkommen)
    common_ids = set.intersection(*id_sets) if id_sets else set()
    if len(common_ids) < N_SAMPLES:
        raise ValueError(f"Zu wenige gemeinsame IDs: {len(common_ids)}")

    # 5) Stichprobe ziehen (reproduzierbar)
    random.seed(SEED)
    sample_ids = random.sample(sorted(common_ids), N_SAMPLES)

    # 6) Output: LaTeX Tabelle (kompakt: Scores pro System)
    systems = sorted(runs.keys())
    header = "ID & " + " & ".join(systems) + r" \\"
    lines = []
    for qid in sample_ids:
        row = [qid]
        for sys in systems:
            score = runs[sys].get(qid, (None, ""))[0]
            row.append("" if score is None else f"{score:.2f}" if isinstance(score, float) else str(score))
        lines.append(" & ".join(row) + r" \\")

    tex = []
    tex.append(r"\begin{table}[H]")
    tex.append(r"\centering")
    tex.append(r"\small")
    tex.append(r"\setlength{\tabcolsep}{4pt}")
    tex.append(r"\begin{tabular}{l" + "c"*len(systems) + r"}")
    tex.append(r"\toprule")
    tex.append(header)
    tex.append(r"\midrule")
    tex.extend(lines)
    tex.append(r"\bottomrule")
    tex.append(r"\end{tabular}")
    tex.append(r"\caption{Stichprobe (Seed=" + str(SEED) + r"): Judge-Scores für fünf zufällig ausgewählte Fragen-IDs über alle Runs.}")
    tex.append(r"\label{tab:stichprobe_judge_scores}")
    tex.append(r"\end{table}")

    out_tex = OUT_DIR / "stichprobe_judge_scores.tex"
    out_tex.write_text("\n".join(tex), encoding="utf-8")

    print("Ausgewählte IDs:", ", ".join(sample_ids))
    print("LaTeX-Tabelle geschrieben:", out_tex)

if __name__ == "__main__":
    main()
