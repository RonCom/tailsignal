"""Clinical narrative generator for the EHR layer.

Notes mimic first-opinion clinic text: abbreviations, misspellings, negations ("no seizures"),
history mentions ("hx sz"), and the ambiguous "fit and well". Each note returns truth labels so
text-mining outcome definitions (Model A2) can be scored for precision and recall.
"""
from __future__ import annotations

from tailsignal.synth import reference as R
from tailsignal.synth.generate import typo

EXAM = ["BAR, MM pink, CRT<2", "QAR, mm pink moist", "BAR. HR/RR wnl", "Bright, alert, responsive. TPR wnl",
        "BAR, H/L ausc wnl", "QAR. Abd palp soft, non painful"]
WELL_OPEN = ["Annual exam.", "Wellness exam + vaccines.", "Yearly check up.", "Annual wellness visit, O has no concerns.",
             "Vacc booster + health check."]
NEG_SZ = ["No seizures.", "no sz activity reported.", "O denies seizures.", "No seizure activity since last visit.",
          "no seizures or collapse."]
NEG_GI = ["No V/D.", "nil V/D.", "O denies vomiting or diarrhoea.", "no vomiting/diarrhea.", "Eating well, no V/D."]
FIT = ["Fit and well.", "fit & well per O.", "O reports fit and well."]
SZ = ["O reports {n} seizure{s} {when}.", "Had a fit {when}.", "siezure {when}, lasted ~{m} min.",
      "Grand mal sz {when}.", "Convulsing {when} per O.", "Seizured {when}, post-ictal on arrival.",
      "Tonic-clonic episode {when}.", "fitting {when}, paddling, salivating."]
WHEN = ["last night", "this AM", "x2 overnight", "yesterday evening", "while asleep"]
GI = ["V+ x{n} since yesterday.", "vomitting and diarrhoea x{n}d.", "D+ {n} days, loose stool.",
      "Vomiting, inappetent.", "Melena noted, D+.", "Vomited x{n} overnight.", "acute V/D."]
NEURO = ["Ataxic on hind limbs.", "Intermittent tremors.", "Wobbly, twitching per O.", "Head tremors noted.",
         "Mild ataxia, no other neuro deficits."]
HIST_SZ = ["Hx of seizures, on phenobarb.", "hx sz (idiopathic epilepsy).", "Known epileptic - on levetiracetam.",
           "hx of fits, well controlled."]
HIST_GI = ["hx of V/D last month, resolved.", "Previous GI upset, now resolved."]
EXTRA_DX = {
    "urinary_tract_infection": ["UTI", "Cystitis - pollakiuria, hematuria", "urinary tract infection",
                                "stranguria, suspect UTI"],
    "pyoderma": ["pyoderma", "superficial bacterial folliculitis", "pustules/epidermal collarettes - pyoderma"],
    "seizure": ["seizure"], "vomiting_diarrhea": ["V/D"], "neuro_signs": ["neuro exam"],
    "elective": ["routine surgery"],
}
PROC = {"dental_cleaning": "COHAT/dental under GA", "spay": "OHE", "neuter": "Castration",
        "mass_removal": "Mass excision", "cruciate_repair": "TPLO", "ivdd_surgery": "Hemilaminectomy"}
COMP = {"hypotension": "hypotensive under GA, fluids bolus", "hypothermia": "hypothermic in recovery, warmed",
        "regurgitation": "regurg on recovery, suctioned", "prolonged_recovery": "slow recovery",
        "airway_obstruction": "BOAS - upper airway obstruction on extubation"}


def note(rng, v: dict, pet, drugs: list, proc: dict | None, known_epileptic: bool) -> tuple[str, dict]:
    pick = lambda xs: xs[int(rng.integers(len(xs)))]
    n = int(rng.integers(1, 5))
    parts = []
    lab = dict(label_seizure=False, label_gi=False, label_neuro=False, label_seizure_negated=False,
               label_seizure_history=False, label_fit_and_well=False)
    ae, vt, dx = v.get("ae_outcome"), v["visit_type"], v["dx"]
    if vt == "wellness":
        parts.append(pick(WELL_OPEN))
    elif vt == "procedure":
        parts.append(f"{PROC.get(v.get('procedure'), 'Procedure')}.")
        if proc:
            parts.append(f"ASA {proc['asa']}.")
            if proc.get("complication"):
                parts.append(COMP[proc["complication"]] + ".")
            if proc.get("death_48h"):
                parts.append("CPA in recovery, CPR unsuccessful.")
            else:
                parts.append(pick(["Recovery uneventful.", "Smooth recovery.", "Recovered well, d/c this PM."]))
                if rng.random() < 0.3:
                    parts.append("Fitted e-collar.")
    else:
        if ae == "seizure":
            s = pick(SZ).format(n=n, s="s" if n > 1 else "", when=pick(WHEN), m=int(rng.integers(1, 6)))
            parts.append(s)
            lab["label_seizure"] = True
        elif ae == "vomiting_diarrhea" or dx == "gastroenteritis":
            parts.append(pick(GI).format(n=n))
            lab["label_gi"] = True
        elif ae == "neuro_signs":
            parts.append(pick(NEURO))
            lab["label_neuro"] = True
        else:
            phrases = R.DX_GAMMA.get(dx) or EXTRA_DX.get(dx, [dx])
            parts.append(("Recheck: " if vt == "recheck" else "Presented for ") + pick(phrases) + ".")
        if v.get("secondary_dx") == "pyoderma":
            parts.append("Also pustules ventral abdomen - pyoderma.")
    parts.append(pick(EXAM) + ".")
    if v.get("bcs") is not None:
        parts.append(f"BCS {v['bcs']}/9, wt {v['weight_kg']}kg.")
    g = v.get("dental_grade")
    if g is not None and not (isinstance(g, float) and g != g):
        parts.append(pick(["Teeth clean.", "Mild tartar."]) if g == 0 else pick([f"Dental gr {g}.", f"PD grade {g}.",
                                                                                 f"Periodontal dz gr {g}."]))
    if known_epileptic and rng.random() < 0.6:
        parts.append(pick(HIST_SZ))
        lab["label_seizure_history"] = True
    if ae != "seizure":
        if rng.random() < (0.25 if vt == "wellness" else 0.08):
            parts.append(pick(NEG_SZ))
            lab["label_seizure_negated"] = True
        if not lab["label_gi"] and rng.random() < (0.2 if vt == "wellness" else 0.15):
            parts.append(pick(NEG_GI))
        if vt == "wellness" and rng.random() < 0.1:
            parts.append(pick(FIT))
            lab["label_fit_and_well"] = True
    if not lab["label_gi"] and rng.random() < 0.03:
        parts.append(pick(HIST_GI))
    if drugs:
        parts.append("Rx: " + ", ".join(drugs) + ".")
    text = " ".join(parts)
    if rng.random() < 0.15:  # one typo in a longer word
        words = text.split(" ")
        idx = [i for i, w in enumerate(words) if len(w) >= 6 and w.isalpha()]
        if idx:
            i = idx[int(rng.integers(len(idx)))]
            words[i] = typo(words[i], rng)
            text = " ".join(words)
    return text, lab
