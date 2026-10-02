"""Outcome identification from clinical notes (Model A2), following Davies et al. (2025).

Stage 1: real VeDDRA term names (from the FDA adverse-event reports) as word-boundary phrases.
Stage 2: + corpus expansion (edit-distance and co-occurrence candidates from the note vocabulary),
         each candidate accepted or rejected in a documented review table (REVIEW).
Stage 3: + rules for negation, history, and known false friends ("fit and well").
Classifier: TF-IDF + logistic regression trained on an annotated sample.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

FDA = Path("data/raw/public/openfda")
OUTCOMES = {
    "seizure": {"veddra": r"seiz|convuls|epilep|^fit$|epileptic fit", "label": "label_seizure",
                "veddra_exclude": r"urination|defecation|ineffective|disease"},
    "gi": {"veddra": r"^vomit|diarrh|tarry", "label": "label_gi", "veddra_exclude": r"virus|allergy|bovine"},
    "neuro": {"veddra": r"ataxi|tremor", "label": "label_neuro", "veddra_exclude": r"hand|circling"},
}
ABBREVIATIONS = {"seizure": ["sz"], "gi": ["v/d", "v+", "d+"], "neuro": []}
# Expert review of stage-2 candidates. Decisions were made by reading each candidate word in isolation,
# without looking at note labels. Unreviewed candidates are rejected and listed in the review log.
# Rule applied by the reviewer to the long tail of misspellings: accept spelling variants (edit distance <= 2, or a
# shared 5-letter prefix) of these clinical head words; reject variants of short or non-specific words
# ("grand" -> "grade", "foam" -> "exam", "head" -> "heart").
TYPO_HEADS = {"seizure", "convulsion", "convulsive", "epilepsy", "epileptic", "vomiting", "diarrhoea", "ataxia",
              "tremor"}
REVIEW = {
    "seizure": {"accept": {"seizures", "sz", "fits", "convulsing"},
                "reject": {"idiopathic", "epilepsy", "phenobarb", "collapse", "controlled", "reports", "had", "per",
                           "last", "since", "and"}},
    "gi": {"accept": {"v/d", "v+", "d+", "vomitting", "vomited", "diarrhea", "vomiting/diarrhea"},
           "reject": {"inappetent"}},
    "neuro": {"accept": {"tremors", "ataxic"},
              "reject": {"neuro", "deficits", "head", "intermittent", "noted", "other"}},
}
NEG = re.compile(r"\b(no|denies|nil|without|not)\b", re.I)
HIST = re.compile(r"\b(hx|history|known epileptic|previous|resolved)\b", re.I)
FALSE_FRIENDS = {"seizure": re.compile(r"\bfit\s*(and|&)\s*well|\bfitted\b", re.I)}
TOKEN = re.compile(r"[a-z][a-z/+\-]*[a-z+]|[a-z]\+|[a-z]/[a-z]", re.I)


def veddra_terms(outcome: str) -> list[str]:
    """Distinct VeDDRA term names for an outcome group, from the real FDA reaction file."""
    r = pd.read_parquet(FDA / "reactions.parquet", columns=["veddra_term_name"]).veddra_term_name.dropna()
    names = pd.Series(r.unique())
    low = names.str.lower()
    spec = OUTCOMES[outcome]
    keep = names[low.str.contains(spec["veddra"]) & ~low.str.contains(spec["veddra_exclude"])]
    return sorted(keep)


def stage1_phrases(terms: list[str]) -> list[str]:
    out = set()
    for t in terms:
        t = re.sub(r"\(.*?\)", "", t.lower())
        t = re.sub(r"\bnos\b", "", t).strip(" ,")
        if t:
            out.add(re.sub(r"\s+", " ", t))
    return sorted(out)


def phrase_regex(phrases: list[str], words: list[str] = ()) -> re.Pattern:
    alts = [re.escape(p) + r"s?" for p in sorted(phrases, key=len, reverse=True)]
    alts += [re.escape(w) for w in sorted(words, key=len, reverse=True)]
    return re.compile(r"(?<![a-z])(" + "|".join(alts) + r")(?![a-z])", re.I)


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def candidates(texts: pd.Series, phrases: list[str], outcome: str, top_cooc: int = 25) -> pd.DataFrame:
    """Stage-2 candidates: edit-distance / shared-prefix variants of stage-1 words, abbreviations, and words
    enriched in notes that hit stage 1 (a co-occurrence stand-in for word2vec similarity)."""
    vocab = Counter(w.lower() for t in texts for w in TOKEN.findall(t))
    heads = {w for p in phrases for w in p.split() if len(w) >= 4}
    rows = []
    for w, n in vocab.items():
        if any(w == h or w == h + "s" for h in heads):
            continue
        for h in heads:
            if (len(w) >= 4 and edit_distance(w, h) <= 2) or (len(w) >= 6 and w[:5] == h[:5]):
                rows.append(dict(word=w, source=f"spelling/morphology of '{h}'", count=n))
                break
    for a in ABBREVIATIONS[outcome]:
        rows.append(dict(word=a, source="abbreviation lexicon", count=vocab.get(a, 0)))
    hit = texts.map(lambda t: bool(phrase_regex(phrases).search(t)))
    hv = Counter(w.lower() for t in texts[hit] for w in set(TOKEN.findall(t)))
    n_hit, n_all = max(hit.sum(), 1), len(texts)
    enr = sorted(((hv[w] / n_hit) / ((vocab[w] + 1) / n_all), w) for w in hv if hv[w] >= 3)
    for ratio, w in reversed(enr[-top_cooc:]):
        rows.append(dict(word=w, source=f"co-occurrence (enrichment {ratio:.0f}x)", count=vocab[w]))
    c = pd.DataFrame(rows).drop_duplicates("word")
    c = c[~c.word.isin(heads | set(phrases))]
    rv = REVIEW[outcome]
    typo_ok = c.source.str.extract(r"of '(\w+)'")[0].isin(TYPO_HEADS) & ~c.word.isin(rv["reject"])
    c["decision"] = np.select([c.word.isin(rv["accept"]), typo_ok, c.word.isin(rv["reject"])],
                              ["accept", "accept (spelling rule)", "reject"], "reject (unreviewed)")
    return c.sort_values(["decision", "count"], ascending=[True, False]).reset_index(drop=True)


class Dictionary:
    def __init__(self, outcome: str, texts: pd.Series):
        self.outcome = outcome
        self.terms = veddra_terms(outcome)
        self.phrases = stage1_phrases(self.terms)
        self.cands = candidates(texts, self.phrases, outcome)
        self.added = sorted(self.cands[self.cands.decision.str.startswith("accept")].word)
        self.re1 = phrase_regex(self.phrases)
        self.re2 = phrase_regex(self.phrases, self.added)

    def stage1(self, texts):
        return texts.map(lambda t: bool(self.re1.search(t)))

    def stage2(self, texts):
        return texts.map(lambda t: bool(self.re2.search(t)))

    def _sentence_hit(self, sent: str, allow_history: bool) -> bool:
        ff = FALSE_FRIENDS.get(self.outcome)
        for m in self.re2.finditer(sent):
            if ff and ff.search(sent[max(0, m.start() - 1):m.end() + 12]):
                continue
            if NEG.search(sent[:m.start()]):
                continue
            if not allow_history and HIST.search(sent):
                continue
            return True
        return False

    def stage3(self, texts, allow_history=False):
        """Current, non-negated mention. allow_history=True also counts history mentions (pre-existing signs)."""
        return texts.map(lambda t: any(self._sentence_hit(s, allow_history) for s in re.split(r"(?<=\.)\s+", t)))


def train_classifier(texts: pd.Series, y: pd.Series, stage2_hit: pd.Series, seed=7, n_hit=1000, n_rand=1000):
    """Annotated sample = n_hit stage-2 hits + n_rand random notes; returns predictions on the remaining notes."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline, make_union
    rng = np.random.default_rng(seed)
    hits = np.flatnonzero(stage2_hit.values)
    a = set(rng.choice(hits, min(n_hit, len(hits)), replace=False))
    rest = np.setdiff1d(np.arange(len(texts)), list(a))
    a |= set(rng.choice(rest, n_rand, replace=False))
    train = np.array(sorted(a))
    test = np.setdiff1d(np.arange(len(texts)), train)
    vec = make_union(TfidfVectorizer(ngram_range=(1, 2), min_df=2, lowercase=True),
                     TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3))
    clf = make_pipeline(vec, LogisticRegression(max_iter=2000, class_weight="balanced", C=4.0))
    clf.fit(texts.iloc[train], y.iloc[train])
    pred = pd.Series(False, index=texts.index)
    pred.iloc[test] = clf.predict(texts.iloc[test]).astype(bool)
    return pred, test


def prf(pred: pd.Series, y: pd.Series) -> dict:
    tp = int((pred & y).sum())
    p = tp / max(int(pred.sum()), 1)
    r = tp / max(int(y.sum()), 1)
    return dict(flagged=int(pred.sum()), true_pos=tp, precision=round(p, 4), recall=round(r, 4),
                f1=round(2 * p * r / max(p + r, 1e-9), 4))


def evaluate(notes: pd.DataFrame, labels: pd.DataFrame, out: Path | None = None) -> tuple[dict, dict]:
    n = notes.merge(labels, on="visit_id")
    res, dicts = {}, {}
    for oc, spec in OUTCOMES.items():
        d = Dictionary(oc, n.text)
        dicts[oc] = d
        y = n[spec["label"]].astype(bool)
        s1, s2, s3 = d.stage1(n.text), d.stage2(n.text), d.stage3(n.text)
        pred, test = train_classifier(n.text, y, s2)
        res[oc] = {"veddra_terms": d.terms, "stage1_phrases": d.phrases, "stage2_added": d.added,
                   "stage1": prf(s1, y), "stage2": prf(s2, y), "stage3": prf(s3, y),
                   "classifier_test": prf(pred.iloc[test], y.iloc[test]),
                   "stage3_on_classifier_test": prf(s3.iloc[test], y.iloc[test]), "true_notes": int(y.sum())}
        if out is not None:
            d.cands.to_csv(out / f"dictionary_review_{oc}.csv", index=False)
    return res, dicts
