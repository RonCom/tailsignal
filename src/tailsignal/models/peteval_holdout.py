"""Independent check of the Model A2 seizure dictionary on PetEVAL. Spec: docs/peteval_holdout_spec.md.

1. My true/false verdicts on the 60 stage-3 hits vs PetEVAL's own ICD-11 chapter labels.
2. Recall on the 150 records PetEVAL labels "Diseases of the nervous system", which I read blind to the
   dictionary output (docs/peteval_nervous_system_labels.csv).

    uv run python -m tailsignal.models.peteval_holdout
"""
from __future__ import annotations

import json

import pandas as pd

from tailsignal.models.ehr_text import Dictionary
from tailsignal.models.peteval_check import OUT, REVIEW, SRC, v2_hit

NERVOUS = "Diseases of the nervous system"
LABELS = "docs/peteval_nervous_system_labels.csv"


def rate(num: int, den: int) -> dict:
    return {"n": int(num), "of": int(den), "rate": round(num / den, 3) if den else None}


def main():
    pe = pd.read_parquet(SRC)
    pe["nervous"] = pe.icd_label.str.contains(NERVOUS)
    d = Dictionary("seizure", pd.read_parquet("data/raw/ehr/ehr_notes.parquet").text)
    pe["s3"] = d.stage3(pe.sentence)
    pe["v2"] = pe.sentence.map(lambda t: v2_hit(d, t)) & pe.s3

    # 1. agreement of my verdicts with PetEVAL's chapter labels
    hits = pe[pe.s3].merge(pd.read_csv(REVIEW), on="id")
    agree = {v: rate(hits[hits.verdict == v].nervous.sum(), (hits.verdict == v).sum())
             for v in ("TP", "uncertain", "FP")}

    # 2. recall inside the nervous-system chapter
    lab = pd.read_csv(LABELS).merge(pe[["id", "s3", "v2"]], on="id")
    sz, pos = lab[lab.label == "seizure"], lab[lab.label.isin(["seizure", "possible"])]
    missed = sz[~sz.s3][["id", "reason"]].to_dict("records")
    res = {
        "agreement_with_icd": agree,
        "nervous_records": int(len(lab)), "labelled_seizure": int(len(sz)), "labelled_possible": int((lab.label == "possible").sum()),
        "recall_frozen_stage3": rate(sz.s3.sum(), len(sz)),
        "recall_v2": rate(sz.v2.sum(), len(sz)),
        "recall_frozen_incl_possible": rate(pos.s3.sum(), len(pos)),
        "true_seizures_lost_by_v2": int((sz.s3 & ~sz.v2).sum()),
        "flags_on_no_seizure_records_frozen": rate(lab[lab.label == "no"].s3.sum(), (lab.label == "no").sum()),
        "missed_by_frozen": missed,
        "expectations": {
            "tp_nervous_at_least_80pct": None, "fp_nervous_at_most_15pct": None,
            "recall_frozen_at_least_70pct": None, "v2_loses_at_most_1": None},
    }
    e = res["expectations"]
    e["tp_nervous_at_least_80pct"] = bool(agree["TP"]["rate"] >= 0.80)
    e["fp_nervous_at_most_15pct"] = bool(agree["FP"]["rate"] <= 0.15)
    e["recall_frozen_at_least_70pct"] = bool(res["recall_frozen_stage3"]["rate"] >= 0.70)
    e["v2_loses_at_most_1"] = bool(res["true_seizures_lost_by_v2"] <= 1)
    (OUT.parent / "peteval_holdout").mkdir(parents=True, exist_ok=True)
    (OUT.parent / "peteval_holdout" / "summary.json").write_text(json.dumps(res, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
