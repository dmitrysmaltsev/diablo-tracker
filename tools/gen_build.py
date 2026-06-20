#!/usr/bin/env python3
"""Generate builds/<id>.json from the maxroll planner — the single source of truth.

Do NOT hand-edit files under builds/. To fix an inaccuracy, fix the resolution
logic here and re-run. To add a build, add an entry to tools/builds_config.json.

Usage:
    python tools/gen_build.py                # regenerate every build in the config
    python tools/gen_build.py <build-id>     # regenerate just one
    python tools/gen_build.py --refresh      # re-download the game-data dictionary

Data sources (see also the maxroll-data-extraction memory):
    planner profile : https://planners.maxroll.gg/profiles/d4/<planner_id>
    game-data dict  : https://assets-ng.maxroll.gg/d4-tools/game/data.min.json
"""
import json
import os
import re
import sys
import datetime
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
CACHE = os.path.join(TOOLS, ".cache")
BUILDS_DIR = os.path.join(ROOT, "builds")
CONFIG = os.path.join(TOOLS, "builds_config.json")

GAMEDATA_URL = "https://assets-ng.maxroll.gg/d4-tools/game/data.min.json"
PLANNER_URL = "https://planners.maxroll.gg/profiles/d4/{}"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


# ---------------------------------------------------------------- fetching ----
def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as r, open(dest, "wb") as f:
        f.write(r.read())


def load_gamedata(refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    dest = os.path.join(CACHE, "gamedata.json")
    if refresh or not os.path.exists(dest):
        print("  downloading game-data dictionary (~11MB)…")
        _download(GAMEDATA_URL, dest)
    return json.load(open(dest, encoding="utf-8"))


def load_planner(planner_id, refresh=False):
    os.makedirs(CACHE, exist_ok=True)
    dest = os.path.join(CACHE, f"planner_{planner_id}.json")
    if refresh or not os.path.exists(dest):
        _download(PLANNER_URL.format(planner_id), dest)
    raw = json.load(open(dest, encoding="utf-8"))
    return json.loads(raw["data"])


# ------------------------------------------------------------- resolution ----
class Resolver:
    """Resolves planner nids/item-ids into readable labels via the game data."""

    TAG = re.compile(r"\{/?c[^}]*\}")          # {c_label}…{/c} colour tags
    UTAG = re.compile(r"\{/?u\}")              # {u}…{/u} underline tags
    ICON = re.compile(r"\{icon:[^}]*\}")       # {icon:bullet,1.2}
    BRACK = re.compile(r"\[[^\]]*\]")          # [{value}*100|1%|] value formatters

    def __init__(self, gd):
        self.gd = gd
        self.items = gd["items"]
        self.affixes = gd["affixes"]
        self.attrs = gd["attributes"]
        self.adesc = gd["attributeDescriptions"]
        self.itemsets = gd.get("itemSets", {})
        self.aff_by_nid = {v["id"]: k for k, v in self.affixes.items()
                           if isinstance(v, dict) and "id" in v}
        # skill id -> name, for resolving {value1} skill refs (e.g. the Paladin
        # aura a tempered "Potency" affix boosts: 2187578 -> "Defiance Aura").
        self.skill_by_id = {v["id"]: v.get("name")
                            for v in gd.get("skills", {}).values()
                            if isinstance(v, dict) and "id" in v}
        # attributeDescriptions keys don't always match the attribute name's case
        self.adesc_ci = {k.lower(): v for k, v in self.adesc.items()}

    def attr_name(self, aid):
        a = self.attrs.get(str(aid)) or self.attrs.get(aid)
        return a["name"] if a else None

    def attr_desc(self, name):
        """Case-insensitive lookup — the source data is inconsistent (e.g.
        attribute 'Flat_Hitpoints_On_Hit…' vs description key '…on_Hit…')."""
        if not name:
            return None
        return self.adesc.get(name) or self.adesc_ci.get(name.lower())

    # {value1} in a template is a tag word (Core, Resolve, Physical, an element…)
    # that the data param-hashes away — recover it from the affix key.
    TAGS = ["Core", "Basic", "Defensive", "Ultimate", "Mastery", "Subterfuge",
            "Companion", "Wrath", "Macabre", "Brawling", "Conjuration",
            "Marksman", "Cutthroat", "Werewolf", "Werebear", "Earth", "Storm",
            "Physical", "Fire", "Cold", "Lightning", "Poison", "Shadow",
            "Resolve", "Overpower", "Ferocity",
            # class resources (e.g. "{value1} Regeneration" -> "Faith Regeneration")
            "Faith", "Fury", "Mana", "Spirit", "Energy", "Essence", "Vigor"]

    def tag_from_key(self, key):
        for t in self.TAGS:
            if key and t in key:
                return t
        return ""

    def clean_affix(self, text, key=None, param=None):
        """Turn an affix description template into a short stat label. `param` is
        the attribute's param id — for {value1} skill refs (e.g. an aura name) it
        resolves to the skill name; otherwise we fall back to a tag from the key."""
        if not text:
            return None
        t = self.TAG.sub("", text)
        tag = self.skill_by_id.get(param) or self.tag_from_key(key)
        t = t.replace("{value1}", tag).replace("{value2}", "")
        t = re.sub(r"\{value\d?\}", "", t)
        t = self.BRACK.sub("", t)
        t = t.replace("+", "")
        t = re.sub(r"\s+", " ", t).strip(" :x")
        # readable phrasings for the templated tag affixes
        m = re.match(r"^to (.+) Skills$", t)
        if m:
            t = f"Ranks to {m.group(1)} Skills"
        m = re.match(r"^(.+?) Maximum Stacks$", t)
        if m:
            t = f"Maximum {m.group(1)} Stacks"
        return t or None

    def affix_meta(self, nid):
        """(key, affixType, category) — affixType 1 = a unique's innate power;
        category -1 = a Transfiguration/implicit damage line."""
        key = self.aff_by_nid.get(nid)
        a = self.affixes.get(key, {})
        return key, a.get("affixType"), a.get("category")

    def affix_label(self, nid):
        """Readable stat label for an explicit/tempered affix, or None if the
        affix has no described attributes (e.g. a unique's innate value)."""
        key = self.aff_by_nid.get(nid)
        if not key:
            return None
        a = self.affixes[key]
        labels = []
        for at in a.get("attributes", []):
            nm = self.attr_name(at.get("id"))
            lab = self.clean_affix(self.attr_desc(nm), key, at.get("param"))
            if lab:
                labels.append(lab)
        if not labels:
            return None
        return " / ".join(dict.fromkeys(labels))

    def item_name(self, gid):
        return self.items.get(gid, {}).get("name", gid)

    def aspect_name(self, nid):
        """Legendary aspect display name, from the affix `suffix` ('of Redirected
        Force' -> 'Redirected Force'). Returns '' for non-aspect entries (e.g. an
        amulet's 2nd, suffix-less slot), which the caller skips."""
        key = self.aff_by_nid.get(nid)
        suffix = (self.affixes.get(key, {}).get("suffix") or "").strip()
        if suffix.lower().startswith("of "):
            return suffix[3:]
        return suffix

    def item_type(self, gid):
        return self.items.get(gid, {}).get("type")

    def magic_type(self, gid):
        return self.items.get(gid, {}).get("magicType")

    def socket_name(self, sid):
        return self.items.get(sid, {}).get("name", sid)

    # -- power / set-bonus prose (a different, richer cleaning than affix labels)
    def clean_power(self, text, values=None):
        if not text:
            return None
        t = self.ICON.sub("", text)
        t = self.TAG.sub("", text if False else t)
        t = self.UTAG.sub("", t)
        # keep the first option of [a|b|c] formatters (usually the literal value)
        t = re.sub(r"\[([^\]|]*)[^\]]*\]", r"\1", t)
        t = t.replace("\r", " ").replace("\n", " ")
        t = re.sub(r"\\[a-zA-Z+]", "", t)   # stray escape artifacts like \+ \x
        t = t.replace("\\", "")
        # substitute Affix_Value_N tokens from the item's explicit values
        if values:
            for i, v in enumerate(values, start=1):
                t = t.replace(f"Affix_Value_{i}", _fmt_num(v))
        # these unique-power values are percentages: "40 increased" -> "40% increased"
        t = re.sub(r"(\d+(?:\.\d+)?) (increased|reduced|decreased)", r"\1% \2", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t or None

    def set_bonuses(self, set_key):
        s = self.itemsets.get(set_key, {})
        out = []
        for b in s.get("bonuses", []):
            a = self.affixes.get(b.get("affix"), {})
            desc = self.clean_power(a.get("desc"))
            if desc:
                out.append(f"({b['required']}) {desc}")
        return s.get("name", set_key), out


def _fmt_num(v):
    if isinstance(v, float):
        if 0 < v < 1:
            return _trim(v * 100) + "%"
        return _trim(v)
    return str(v)


def _trim(v):
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


# --------------------------------------------------------------- building -----
# Equipment slots keyed by the game-data item `type` (robust across builds).
ARMOR_SLOTS = {"Helm": "Helm", "ChestArmor": "Chest", "Gloves": "Gloves",
               "Legs": "Pants", "Boots": "Boots"}
JEWELRY_SLOTS = {"Amulet": "Amulet", "Ring": "Ring"}
OFFHAND_TYPES = {"Shield", "Focus", "Totem", "OffHandFocus"}
NON_WEAPON = set(ARMOR_SLOTS) | set(JEWELRY_SLOTS) | OFFHAND_TYPES | {
    "Charm", "HoradricSeal"}

# Output order for equipment.
SLOT_ORDER = ["Helm", "Chest", "Gloves", "Pants", "Boots", "Amulet",
              "Ring 1", "Ring 2", "Weapon", "Off-Hand / Shield"]


def magic_to_type(m):
    return {1: "rare", 2: "unique", 3: "set", 4: "unique"}.get(m, "rare")


def build_equipment_slot(res, item, slot_label):
    gid = item["id"]
    mtype = res.magic_type(gid)
    typ = magic_to_type(mtype)
    # An imprinted legendary aspect defines the item — surface its name and mark
    # the slot "legendary" so the UI shows the aspect in place of the base name.
    aspect = ""
    for asp in item.get("aspects", []):
        nm = res.aspect_name(asp.get("nid"))
        if nm:
            aspect, typ = nm, "legendary"
            break
    # `normal` keeps explicits in their planner order. Two kinds of "Unique Effect"
    # lines exist and maxroll renders them differently:
    #   - a Mythic/uber's innate power (affixType 1) is pulled to the BOTTOM (e.g.
    #     the Heir of Perdition helm, magicType 4);
    #   - a regular unique's power stays where it sits in the planner order — whether
    #     it's an affixType-1 innate (e.g. the Ward of the White Dove shield, where
    #     it's the 1st affix) or an in-place item power (key == item id, e.g. the
    #     chest's effect is its 2nd affix).
    # The Transfiguration/implicit line (cat -1) is always last, and the masterwork
    # pick (upgradePriority 1) is moved to the front.
    normal, innate_fx, trailing, mw, verify = [], [], [], None, False
    for ex in item.get("explicits", []):
        key, atype, cat = res.affix_meta(ex["nid"])
        if atype == 1:                             # unique's innate power
            if mtype == 4:                         # Mythic/uber -> bottom
                innate_fx.append("Unique Effect")
            else:                                  # regular unique -> planner order
                normal.append("Unique Effect")
            continue
        if cat == -1:                              # Transfiguration / implicit -> last
            lab = res.affix_label(ex["nid"])
            if lab:
                trailing.append(lab)
            continue
        if key == gid:                             # in-place unique effect (e.g. chest)
            normal.append("Unique Effect")
            continue
        lab = res.affix_label(ex["nid"])
        if not lab:
            continue
        if ex.get("upgradePriority") == 1:
            mw = lab
        normal.append(lab)
    if mw and mw in normal:                        # masterwork pick goes first,
        normal.remove(mw)                          # but never above a leading
        pos = 1 if normal[:1] == ["Unique Effect"] else 0   # unique effect
        normal.insert(pos, mw)
    # order: explicits in planner order, then the innate power, then implicit damage
    affixes = normal + innate_fx + trailing
    tempering = [res.affix_label(t["nid"]) for t in item.get("tempered", [])]
    tempering = [t for t in tempering if t]
    gems, runes = [], []
    for s in item.get("sockets", []):
        (gems if s.startswith("Gem") else runes).append(res.socket_name(s))
    slot = {
        "slot": slot_label,
        "item": res.item_name(gid),
        "type": typ,
        "aspect": aspect,
        "affixes": affixes,
        "tempering": tempering,
        "gem": _join_gems(gems),
        "verify": verify,
    }
    if runes:
        slot["runes"] = runes
    return slot


def build_seal_slot(res, item):
    """Render the Legendary Horadric Seal as its own slot. Its lines are described
    inconsistently — some via attributes (affix_label), the +Charm Slot via prose
    (clean_power) — so try the label first and fall back to the cleaned power."""
    gid = item["id"]
    affixes = []
    for ex in item.get("explicits", []):
        key = res.aff_by_nid.get(ex["nid"])
        lab = res.affix_label(ex["nid"]) or res.clean_power(
            res.affixes.get(key, {}).get("desc"), ex.get("values"))
        if lab:
            affixes.append(lab)
    return {
        "slot": "Seal",
        "item": item.get("name") or res.item_name(gid),
        "type": "legendary",
        "aspect": "",
        "affixes": affixes,
        "tempering": [],
        "gem": "",
        "verify": False,
    }


def _join_gems(gems):
    """Collapse duplicate sockets, e.g. two Grand Ruby -> '2× Grand Ruby'."""
    if not gems:
        return ""
    out = []
    seen = {}
    for g in gems:
        if g not in seen:
            seen[g] = len(out)
            out.append([g, 1])
        else:
            out[seen[g]][1] += 1
    return ", ".join(f"{n}× {name}" if n > 1 else name for name, n in out)


def classify(res, item):
    """Return (category, slot_label) for an equipped item."""
    t = res.item_type(item["id"])
    if t in ARMOR_SLOTS:
        return "gear", ARMOR_SLOTS[t]
    if t == "Amulet":
        return "gear", "Amulet"
    if t == "Ring":
        return "ring", "Ring"
    if t in OFFHAND_TYPES:
        return "gear", "Off-Hand / Shield"
    if t == "Charm":
        return "charm", None
    if t == "HoradricSeal":
        return "seal", None
    return "weapon", "Weapon"     # any weapon type


def build_talisman_slots(res, charms, seal_name):
    """Group set charms into one slot per set; emit unique charms individually."""
    slots = []
    sets = {}      # set_key -> list of charm item defs
    uniques = []
    for c in charms:
        gid = c["id"]
        idef = res.items.get(gid, {})
        if res.magic_type(gid) == 3 and idef.get("set"):
            sets.setdefault(idef["set"], []).append(c)
        else:
            uniques.append(c)

    for set_key, members in sets.items():
        members.sort(key=lambda m: m["id"])        # deterministic charm order
        set_name, bonuses = res.set_bonuses(set_key)
        names = [res.item_name(m["id"]) for m in members]
        where = f" equipped in your {seal_name}" if seal_name else ""
        note = (f"{len(members)}-piece charm set{where}: "
                f"{_human_list(names)}. Each charm gives +All Stats and one "
                f"elemental Resistance.")
        slots.append({
            "slot": "Charms",
            "item": f"{set_name} ({len(members)}pc)",
            "type": "set",
            "aspect": "",
            "note": note,
            "bonuses": bonuses,
            "verify": False,
        })

    for c in uniques:
        gid = c["id"]
        key = c["id"]
        # unique charm power lives on the matching unique affix (by id string)
        affix_key = _unique_affix_key(res, gid)
        values = [v for ex in c.get("explicits", []) for v in ex.get("values", [])]
        desc = None
        if affix_key:
            desc = res.clean_power(res.affixes[affix_key].get("desc"), values)
        slot = {
            "slot": "Unique Charm",
            "item": res.item_name(gid),
            "type": "unique",
            "aspect": "",
            "note": desc or "",
            # flag only if a value token couldn't be resolved at all
            "verify": bool(desc and "Affix_Value_" in desc),
        }
        slots.append(slot)
    return slots


def _unique_affix_key(res, gid):
    """A unique charm 'Talisman_Charm_Unique_<X>' carries the power of unique <X>."""
    m = re.search(r"Unique_(.+)$", gid)
    if m and m.group(1) in res.affixes:
        return m.group(1)
    # fall back: an affix key embedded in the id tail
    tail = gid.split("Unique_")[-1]
    return tail if tail in res.affixes else None


def _human_list(names):
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + ", and " + names[-1]


def generate(cfg, res, planner):
    profiles = planner["profiles"]
    prof = next(p for p in profiles if p["name"] == cfg["profile"])
    item_defs = planner["items"]

    gear, rings, charms, weapons, seal_item = {}, [], [], [], None
    for sidx, iid in sorted(prof["items"].items(), key=lambda kv: int(kv[0])):
        item = item_defs.get(str(iid))
        if not item:
            continue
        cat, label = classify(res, item)
        if cat == "gear":
            gear[label] = item
        elif cat == "ring":
            rings.append(item)
        elif cat == "weapon":
            weapons.append(item)
        elif cat == "charm":
            charms.append(item)
        elif cat == "seal":
            seal_item = item
    seal_name = res.item_name(seal_item["id"]) if seal_item else None

    slots = []
    # ordered equipment
    for label in ["Helm", "Chest", "Gloves", "Pants", "Boots", "Amulet"]:
        if label in gear:
            slots.append(build_equipment_slot(res, gear[label], label))
    for i, item in enumerate(rings, start=1):
        slots.append(build_equipment_slot(res, item, f"Ring {i}"))
    for i, item in enumerate(weapons, start=1):
        label = "Weapon" if len(weapons) == 1 else f"Weapon {i}"
        slots.append(build_equipment_slot(res, item, label))
    if "Off-Hand / Shield" in gear:
        slots.append(build_equipment_slot(res, gear["Off-Hand / Shield"],
                                          "Off-Hand / Shield"))
    # the Horadric Seal that holds the charms, then the talismans / charms
    if seal_item:
        slots.append(build_seal_slot(res, seal_item))
    slots.extend(build_talisman_slots(res, charms, seal_name))

    return {
        "id": cfg["id"],
        "name": cfg["name"],
        "class": cfg["class"],
        "source": cfg.get("source", ""),
        "planner": f"https://maxroll.gg/d4/planner/{cfg['planner_id']}",
        "patch": cfg.get("patch", ""),
        "updated": datetime.date.today().isoformat(),
        "profile": cfg["profile"],
        "notes": cfg.get("notes", ""),
        "slots": slots,
    }


# ------------------------------------------------------------------- main -----
def main(argv):
    refresh = "--refresh" in argv
    wanted = [a for a in argv if not a.startswith("-")]
    cfg_all = json.load(open(CONFIG, encoding="utf-8"))["builds"]
    targets = [b for b in cfg_all if not wanted or b["id"] in wanted]
    if not targets:
        print(f"No matching build(s) for {wanted}; known: "
              f"{[b['id'] for b in cfg_all]}")
        return 1

    print("Loading game data…")
    gd = load_gamedata(refresh=refresh)
    res = Resolver(gd)

    index = []
    for b in cfg_all:                       # rebuild the full index from config
        index.append({"id": b["id"], "name": b["name"], "class": b["class"],
                      "updated": datetime.date.today().isoformat()})

    for cfg in targets:
        print(f"Generating {cfg['id']} (planner {cfg['planner_id']}, "
              f"{cfg['profile']})…")
        planner = load_planner(cfg["planner_id"], refresh=refresh)
        build = generate(cfg, res, planner)
        out = os.path.join(BUILDS_DIR, f"{cfg['id']}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(build, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  wrote {out}  ({len(build['slots'])} slots)")

    with open(os.path.join(BUILDS_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  wrote builds/index.json  ({len(index)} build(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
