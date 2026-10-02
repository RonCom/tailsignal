"""Real-text check of the Model A2 seizure dictionary on SAVSNET PetEVAL (UK first-opinion clinic notes).

The dictionaries are frozen from the synthetic corpus (no tuning on PetEVAL). Every stage-3 hit was read and judged
by hand (docs/peteval_seizure_review.csv). A post-hoc rule set (V2), written after reading the hits, is reported
separately; its precision on this same sample is optimistic.

    uv run python -m tailsignal.models.peteval_check
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from tailsignal.models.ehr_text import FALSE_FRIENDS, HIST, NEG, Dictionary

SRC = Path("data/raw/public/peteval/data/test-00000-of-00001.parquet")
REVIEW = Path("docs/peteval_seizure_review.csv")
OUT = Path("reports/model_a2/peteval")
# Post-hoc (V2): non-clinical senses of "fit" seen in the UK notes
FIT_V2 = re.compile(r"\bfit\s+(for|to|enough|in|and|&)\b|\bfits?\s+(with|well|fine|in|really|of)\b|"
                    r"\b(very|nice|coughing?|coughin|sneezing)\s+fits?\b|\bfit\s+\d", re.I)


def v2_hit(d: Dictionary, text: str) -> bool:
    for sent in re.split(r"(?<=\.)\s+", text):
        for m in d.re2.finditer(sent):
            ctx = sent[max(0, m.start() - 12):m.end() + 14]
            if m.group(0).lower().startswith("fit") and FIT_V2.search(ctx):
                continue
            if FALSE_FRIENDS["seizure"].search(sent[max(0, m.start() - 1):m.end() + 12]):
                continue
            if NEG.search(sent[:m.start()]) or HIST.search(sent):
                continue
            return True
    return False


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pe = pd.read_parquet(SRC)
    syn = pd.read_parquet("data/raw/ehr/ehr_notes.parquet").text
    d = Dictionary("seizure", syn)
    pe["s1"], pe["s2"], pe["s3"] = d.stage1(pe.sentence), d.stage2(pe.sentence), d.stage3(pe.sentence)
    pe["v2"] = pe.sentence.map(lambda t: v2_hit(d, t)) & pe.s3
    rv = pd.read_csv(REVIEW)
    hits = pe[pe.s3].merge(rv, on="id", how="left")
    unreviewed = hits[hits.verdict.isna()].id.tolist()

    def prec(df):
        n = len(df)
        tp = int((df.verdict == "TP").sum())
        unc = int((df.verdict == "uncertain").sum())
        return dict(flagged=n, true=tp, uncertain=unc, false=n - tp - unc,
                    precision_strict=round(tp / max(n, 1), 3), precision_incl_uncertain=round((tp + unc) / max(n, 1), 3))

    fp = hits[hits.verdict == "FP"]
    res = dict(records=len(pe), stage1_hits=int(pe.s1.sum()), stage2_hits=int(pe.s2.sum()),
               stage3_frozen=prec(hits), stage3_v2_posthoc=prec(hits[hits.id.isin(pe[pe.v2].id)]),
               false_positives_from_fit=int(fp.reason.str.contains(r"\bfit", case=False).sum()),
               true_positives_lost_by_v2=int(((hits.verdict == "TP") & ~hits.id.isin(pe[pe.v2].id)).sum()),
               unreviewed_ids=unreviewed)
    syn_lab = pd.read_parquet("data/truth/ehr/note_labels.parquet")
    n = pd.read_parquet("data/raw/ehr/ehr_notes.parquet")[["visit_id", "text"]].merge(syn_lab, on="visit_id")
    v2s = n.text.map(lambda t: v2_hit(d, t))
    y = n.label_seizure
    res["v2_on_synthetic"] = dict(precision=round(float((v2s & y).sum() / max(v2s.sum(), 1)), 3),
                                  recall=round(float((v2s & y).sum() / y.sum()), 3))
    hits.to_csv(OUT / "stage3_hits_reviewed.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
