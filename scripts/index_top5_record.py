#!/usr/bin/env python3
"""指数上位5頭の成績をレース後に記録し、累計の勝率・複勝率を集計する。

使い方: python3 scripts/index_top5_record.py <指数入り出馬表JSON> <結果JSON> [--record <記録JSON>]

定義:
- 「指数上位5頭」= そのレースの指数入り出馬表（data/entry_index/<slug>.json、
  scripts/build_entry_index.py が生成）で前走指数（horses[].index、能力指数v0.2）が
  高い順の5頭。指数なし（index が null）の馬は対象外。
  指数のある馬が5頭未満なら、その全頭を対象とし頭数を記録に残す。
- 副系列として、近2走平均（horses[].index_avg2）の上位5頭も同じ形式で記録する。
- 着順は結果JSON（data/results/<race_id>.json）の runners[].rank を馬名で照合する。
- 勝ち = 1着、複勝 = 3着以内。勝率 = 勝ち数 / 出走数、複勝率 = 複勝数 / 出走数
  （パーセント・小数1桁）。「出走数」は対象馬のうち結果JSONに数値の着順がある頭数。
  結果に名前がない馬・着順が null の馬（取消・除外・中止など）は出走数に数えず、
  finish: null として記録に残す。
- 累計は記録済み全レースの合算（馬単位＝延べ頭数）。

記録ファイル data/index/top5_record.json にレース単位で追記する。
同じ race_id で再実行した場合は、そのレースの記録を置き換える（冪等・重複しない）。
"""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP_N = 5

# 系列キー -> (出馬表の指数フィールド, 表示名)
SERIES = {
    "last_index": ("index", "前走指数"),
    "avg2": ("index_avg2", "近2走平均"),
}


def rate(numer, denom):
    return round(100.0 * numer / denom, 1) if denom else 0.0


def empty_summary():
    return {"starts": 0, "wins": 0, "places": 0, "win_rate": 0.0, "place_rate": 0.0}


def empty_store():
    return {
        "version": 1,
        "index_version": "0.2",
        "description": "指数上位5頭（前走指数／近2走平均）のレース後成績記録。勝率・複勝率は記録済み全レースの累計。",
        "races": [],
        "cumulative": {
            "races_recorded": 0,
            "last_index": empty_summary(),
            "avg2": empty_summary(),
        },
    }


def top_series(horses, field):
    """指数フィールドの高い順に最大TOP_N頭を返す（指数なしは除外）。"""
    indexed = [h for h in horses if h.get(field) is not None]
    indexed.sort(key=lambda h: -h[field])
    return indexed[:TOP_N], len(indexed)


def build_series_record(horses, field, finishes):
    top, indexed_count = top_series(horses, field)
    rows = []
    starts = wins = places = 0
    for i, h in enumerate(top, 1):
        finish = finishes.get(h["name"])
        ran = isinstance(finish, int)
        if ran:
            starts += 1
            if finish == 1:
                wins += 1
            if finish <= 3:
                places += 1
        rows.append({
            "index_rank": i,
            "name": h["name"],
            "index_value": h[field],
            "finish": finish if ran else None,
        })
    return {
        "indexed_horses": indexed_count,
        "count": len(top),
        "top": rows,
        "starts": starts,
        "wins": wins,
        "places": places,
        "win_rate": rate(wins, starts),
        "place_rate": rate(places, starts),
    }


def recompute_cumulative(store):
    cum = {"races_recorded": len(store["races"])}
    for key in SERIES:
        s = empty_summary()
        for race in store["races"]:
            rec = race["series"][key]
            s["starts"] += rec["starts"]
            s["wins"] += rec["wins"]
            s["places"] += rec["places"]
        s["win_rate"] = rate(s["wins"], s["starts"])
        s["place_rate"] = rate(s["places"], s["starts"])
        cum[key] = s
    store["cumulative"] = cum


def main():
    ap = argparse.ArgumentParser(description="指数上位5頭の成績を記録する")
    ap.add_argument("entry_index", help="指数入り出馬表JSON (data/entry_index/<slug>.json)")
    ap.add_argument("result", help="結果JSON (data/results/<race_id>.json)")
    ap.add_argument("--record", default=str(ROOT / "data" / "index" / "top5_record.json"),
                    help="記録JSONのパス (既定: data/index/top5_record.json)")
    args = ap.parse_args()

    entry = json.loads(Path(args.entry_index).read_text(encoding="utf-8"))
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))

    horses = entry.get("horses") or entry.get("runners") or []
    finishes = {r["name"]: r.get("rank") for r in result.get("runners", [])}

    race_id = result.get("race_id")
    if not race_id:
        raise SystemExit("結果JSONに race_id がありません")

    now = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")
    record = {
        "race_id": race_id,
        "race_name": result.get("race_name") or entry.get("race_name"),
        "date": result.get("date"),
        "track": result.get("track"),
        "entry_index_slug": Path(args.entry_index).stem,
        "recorded_at": now,
        "series": {
            key: build_series_record(horses, field, finishes)
            for key, (field, _label) in SERIES.items()
        },
    }

    record_path = Path(args.record)
    if record_path.exists():
        store = json.loads(record_path.read_text(encoding="utf-8"))
    else:
        store = empty_store()

    # 冪等: 同じ race_id の記録は置き換える
    store["races"] = [r for r in store["races"] if r["race_id"] != race_id]
    store["races"].append(record)
    store["races"].sort(key=lambda r: (r.get("date") or "", r["race_id"]))
    recompute_cumulative(store)

    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"記録: {record['race_name']} ({record['date']}, race_id {race_id}) -> {record_path}")
    for key, (_field, label) in SERIES.items():
        rec = record["series"][key]
        names = "、".join(f"{t['name']}({t['finish']}着)" if t["finish"] is not None else f"{t['name']}(着順なし)"
                          for t in rec["top"])
        print(f"  {label} 上位{rec['count']}頭: {names}")
        print(f"    このレース: 出走{rec['starts']} 勝ち{rec['wins']} 複勝{rec['places']} "
              f"勝率{rec['win_rate']}% 複勝率{rec['place_rate']}%")
    cum = store["cumulative"]
    print(f"累計 ({cum['races_recorded']}レース):")
    for key, (_field, label) in SERIES.items():
        s = cum[key]
        print(f"  {label}: 出走{s['starts']} 勝ち{s['wins']} 複勝{s['places']} "
              f"勝率{s['win_rate']}% 複勝率{s['place_rate']}%")


if __name__ == "__main__":
    main()
