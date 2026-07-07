#!/usr/bin/env python3
"""Build qualitative.json for the APIVOT site's Qualitative Comparisons section.

Folder format (one folder per comparison sample, named sample_*):

  qualitative/
    sample_01/
      meta.json            # see fields below
      initial.png          # shared initial state (any image extension)
      ours/
        1_grasps bowl.png   # key rendered states; leading number = order,
        2_clears space.png  # text after the underscore = the caption shown
        3_final.png         # under that frame (this is the step label now)
      baseline/
        1_places bowl.png
        2!_collision.png    # "!" after the number = a mistake frame (red)

The per-frame caption is the label under each rollout image, so the
action<->image correspondence is automatic. A separate plan.txt is OPTIONAL
and no longer displayed (kept only if present, for your own reference).

meta.json:
  {
    "instruction":       "Place the bowls inside the minifridge.",
    "baseline_name":     "VLM-TAMP",       # label for the baseline row
    "ours_outcome":      "feasible plan",  # short note next to the ours badge
    "baseline_outcome":  "collision"       # short note next to the baseline badge
  }

Notes:
  - "ours" is always rendered as success (green); "baseline" as failure (red).
  - You can have fewer rendered states than plan actions — the states form the
    filmstrip, the full plan is listed separately below it.
  - Captions are optional: a frame named just "2.png" gets no caption.

Marking mistakes (useful when the baseline botches several steps):
  - In plan.txt, prefix a line with "!" to flag it as a mistake action
    (rendered red).  e.g.   !place(bowl#2, fridge, [..])   # collides
  - In a frame filename, put "!" right after the order number to flag a bad
    rendered state (red ring).  e.g.   3!_collision.png
  - Any number of steps/frames can be flagged. If no baseline frame is flagged,
    the last baseline frame is treated as the failure point by default.

Run:  python3 build_qualitative.py
Output: qualitative.json (consumed by projects/apivot.html)
"""
import os, re, json, glob, random

HERE = os.path.dirname(os.path.abspath(__file__))
IMG_EXT = ('.png', '.jpg', '.jpeg', '.webp', '.gif')

def frames(folder):
    out = []
    if not os.path.isdir(folder):
        return out
    files = [f for f in os.listdir(folder) if f.lower().endswith(IMG_EXT)]
    def key(f):
        m = re.match(r'\s*(\d+)', f)
        return (int(m.group(1)) if m else 1e9, f)
    for f in sorted(files, key=key):
        stem = os.path.splitext(f)[0]
        # <order>[!]<sep><caption>   "!" right after the number flags a mistake frame
        m = re.match(r'\s*\d+(!?)[ _-]*(.*)', stem)
        bad = bool(m and m.group(1))
        caption = (m.group(2).replace('_', ' ').strip() if m else '')
        rel = os.path.relpath(os.path.join(folder, f), HERE).replace(os.sep, '/')
        out.append({'img': 'qualitative/' + rel, 'caption': caption, 'bad': bad})
    return out

def plan(folder):
    p = os.path.join(folder, 'plan.txt')
    if not os.path.isfile(p):
        return []
    steps = []
    with open(p) as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            bad = ln.startswith('!')                # "!" prefix flags a mistake action
            steps.append({'text': ln.lstrip('!').strip(), 'bad': bad})
    return steps

def initials(sample):
    # every image whose name starts with "initial" (initial.png, initial_fridge.png,
    # initial_braiser1.png, ...), each with a label derived from the filename:
    #   initial_fridge.png    -> "fridge"
    #   initial_braiser1.png  -> "braiser 1"
    out = []
    cands = sorted(f for f in os.listdir(sample)
                   if f.lower().startswith('initial') and f.lower().endswith(IMG_EXT))
    for f in cands:
        stem = os.path.splitext(f)[0]
        rest = re.sub(r'^initial[ _\-]*', '', stem, flags=re.I).replace('_', ' ').strip()
        rest = re.sub(r'([A-Za-z])(\d)', r'\1 \2', rest)   # braiser1 -> braiser 1
        label = rest if rest else 'initial state'
        rel = os.path.relpath(os.path.join(sample, f), HERE).replace(os.sep, '/')
        out.append({'img': 'qualitative/' + rel, 'label': label})
    # show at most two initial states. If there are more (e.g. braiser 1,
    # braiser 2, fridge), collapse the braisers to the first one, then cap to 2.
    if len(out) > 2:
        braisers = [x for x in out if x['label'].lower().startswith('braiser')]
        others = [x for x in out if not x['label'].lower().startswith('braiser')]
        out = ((braisers[:1]) + others)[:2]
    # display order: fridge first, then braiser (store-leftovers shows both)
    prio = lambda x: (0 if 'fridge' in x['label'].lower() else 1 if 'braiser' in x['label'].lower() else 2)
    out.sort(key=prio)
    return out

samples = []
for sample in sorted(glob.glob(os.path.join(HERE, 'sample_*'))):
    if not os.path.isdir(sample):
        continue
    sid = os.path.basename(sample)
    meta_path = os.path.join(sample, 'meta.json')
    meta = json.load(open(meta_path)) if os.path.isfile(meta_path) else {}
    ours_frames = frames(os.path.join(sample, 'ours'))
    base_frames = frames(os.path.join(sample, 'baseline'))
    if not ours_frames and not base_frames:
        print(f'  skip {sid}: no frames found')
        continue
    samples.append({
        'id': sid,
        '_task': meta.get('task', ''),
        'instruction': meta.get('instruction', ''),
        'description': meta.get('description', ''),
        'initials': initials(sample),
        'ours': {
            'name': meta.get('ours_name', 'APIVOT (Ours)'),
            'outcome': meta.get('ours_outcome', 'feasible plan'),
            'success': True,
            'frames': ours_frames,
            'plan': plan(os.path.join(sample, 'ours')),
        },
        'baseline': {
            'name': meta.get('baseline_name', 'Baseline'),
            'outcome': meta.get('baseline_outcome', 'failure'),
            'success': False,
            'frames': base_frames,
            'plan': plan(os.path.join(sample, 'baseline')),
        },
    })

# display order: storing leftovers, then containment, then sorting
TASK_ORDER = {'storing_leftovers': 0, 'containment': 1, 'sorting': 2}
samples.sort(key=lambda s: (TASK_ORDER.get(s.get('_task', ''), 99), s['id']))
for s in samples:
    s.pop('_task', None)

out = os.path.join(HERE, 'qualitative.json')
json.dump(samples, open(out, 'w'), indent=2)
print(f'wrote {out}: {len(samples)} sample(s)')
for s in samples:
    print(f"  {s['id']}: ours {len(s['ours']['frames'])} frames / {len(s['ours']['plan'])} actions,"
          f" baseline {len(s['baseline']['frames'])} frames / {len(s['baseline']['plan'])} actions")
