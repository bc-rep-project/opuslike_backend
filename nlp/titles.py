import os, re, math
from collections import Counter

TEMPLATES = [
    "I Tried {X} for {N} Days — Here’s What Happened",
    "The {X} Mistake Everyone Makes (and How to Fix It)",
    "{X}: 5 Things I Wish I Knew",
    "We Tested {X} So You Don’t Have To",
    "Do This Before You {X}",
    "Stop Doing This with {X}",
    "The Secret to {X} Nobody Told You",
    "Why Your {X} Isn’t Working (Do This Instead)",
    "{X} in 10 Minutes (Step-by-Step)",
]

def top_phrases(text: str, k=8):
    text = re.sub(r"\s+", " ", text or "").strip()
    # tokenize
    toks = [t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9']+", text)]
    if not toks: return []
    # remove common stopwords
    STOP = set("""the of and to a in it is that for on with as this you your i we they are was be have not do from or if so but at by about into out up down over under after before then just very really can get make use using more most less few many much any every some no yes one two three how why what when where who""".split())
    toks = [t for t in toks if t not in STOP and len(t) > 2]
    # build ngrams
    grams = []
    for n in (1,2,3):
        for i in range(len(toks)-n+1):
            grams.append(" ".join(toks[i:i+n]))
    counts = Counter(grams)
    # prefer 2-3 grams slightly
    for g in list(counts):
        if len(g.split())==2: counts[g] *= 1.3
        if len(g.split())==3: counts[g] *= 1.5
    best = [g for g,_ in counts.most_common(k*3)]
    # prune overlaps
    keep=[]
    for g in best:
        if not any((g in h) or (h in g) for h in keep):
            keep.append(g)
        if len(keep)>=k: break
    return keep

def render_templates(phrases):
    out = []
    for p in phrases:
        X = p.title()
        for t in TEMPLATES[:6]:
            s = t.replace("{X}", X).replace("{N}", "30")
            out.append(s)
    # dedupe + truncate
    seen=set(); res=[]
    for s in out:
        key = s.lower()
        if key not in seen:
            seen.add(key)
            res.append(s)
        if len(res)>=12: break
    return res

def suggest_titles(text: str, extra_context: str | None = None, use_llm: bool = False):
    """Return a list of up to ~12 title suggestions. If use_llm=True and OPENAI_API_KEY set, try LLM first."""
    if use_llm and os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI
            client = OpenAI()
            prompt = "Write 10 viral YouTube titles (<= 60 chars) for this transcript. Avoid clickbait, be specific.\n\n" + (extra_context or "") + "\n\nTranscript:\n" + (text[:10000] if text else "")
            r = client.chat.completions.create(model=os.getenv("OPENAI_MODEL","gpt-4o-mini"), messages=[{"role":"user","content":prompt}], temperature=0.7)
            cand = r.choices[0].message.content.splitlines()
            cand = [re.sub(r"^\d+[\).]\s*","", c).strip() for c in cand if c.strip()]
            cand = [c for c in cand if 8 <= len(c) <= 70][:12]
            if cand: return cand
        except Exception:
            pass
    phrases = top_phrases(text)
    return render_templates(phrases) or ["Behind the Scenes", "What No One Told You", "This Changed Everything"]
