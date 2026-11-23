#!/usr/bin/env python3
"""指数入り出馬表を作る。

使い方: python3 scripts/build_entry_index.py <出馬表JSON> <出力slug>

出馬表JSONは data/entries/<race_id>.json 形式（runners: number/name/jockey...）
でも、{horses: [{name, jockey}, ...]} 形式（想定版）でもよい。
data/index/ability_index.json の蓄積から各馬の指数履歴を引いて、
前走指数・前走レース/着順・近2走平均を付けた表を data/entry_index/<slug>.json に出す。
指数データがない馬は index: null（指数なし）として明示する。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_history():
    p = ROOT / "data" / "index" / "ability_index.json"
    hist = {}
    if not p.exists():
        return hist
    data = json.loads(p.read_text(encoding="utf-8"))
    for race in data["races"]:
        for r in race["runners"]:
            hist.setdefault(r["name"], []).append({
                "race_id": race["race_id"],
                "race_name": race["race_name"],
                "date": race["date"],
                "track": race["track"],
                "course": race.get("course"),
                "going": race.get("going"),
                "rank": r["rank"],
                "index": r["index"],
                "index_rank": r["index_rank"],
                "popularity": r["popularity"],
                "win_odds": r["win_odds"],
                "value_gap": r["value_gap"],
            })
    for v in hist.values():
        v.sort(key=lambda x: x["date"])
    return hist


def main():
    if len(sys.argv) != 3:
        sys.exit("使い方: python3 scripts/build_entry_index.py <出馬表JSON> <出力slug>")
    src = Path(sys.argv[1])
    slug = sys.argv[2]
    entry = json.loads(src.read_text(encoding="utf-8"))
    raw = entry.get("runners") or entry.get("horses") or []
    hist = load_history()
    rows = []
    for h in raw:
        name = h.get("name")
        runs = hist.get(name, [])
        last = runs[-1] if runs else None
        last2 = runs[-2:]
        avg2 = round(sum(r["index"] for r in last2) / len(last2), 1) if last2 else None
        rows.append({
            "number": h.get("number"),
            "name": name,
            "jockey": h.get("jockey"),
            "index": last["index"] if last else None,
            "prev_race": last,
            "index_avg2": avg2,
            "runs_indexed": len(runs),
        })
    indexed = sorted([r for r in rows if r["index"] is not None], key=lambda x: -x["index"])
    for i, r in enumerate(indexed, 1):
        r["index_rank_in_race"] = i
    out_dir = ROOT / "data" / "entry_index"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {
        "race_name": entry.get("race_name") or (entry.get("race") or {}).get("race_name"),
        "source": str(src),
        "index_version": "0.1",
        "horses": rows,
    }
    p = out_dir / f"{slug}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {p} ({len(rows)}頭 / 指数あり {len(indexed)}頭)")
    for r in indexed:
        prev = r["prev_race"]
        print(f"  指数{r['index_rank_in_race']:>2}位 {r['index']:>6} (近2走平均 {r['index_avg2']}) {r['name']} "
              f"［前走 {prev['race_name']} {prev['rank']}着］")
    for r in rows:
        if r["index"] is None:
            print(f"  指数なし {r['name']}")


if __name__ == "__main__":
    main()
