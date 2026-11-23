#!/usr/bin/env python3
"""独自能力指数 v0.1（試作）

data/results/<race_id>.json の結果データから、各馬の能力指数を計算し、
data/index/ability_index.json に保存する。

指数の設計（レース内相対評価）:
  指数 = 100
       + タイムスコア   : (出走馬平均タイム - 当該馬タイム) × 10   … 0.1秒 = 1点
       + 上がりスコア   : (出走馬平均上がり3F - 当該馬上がり3F) × 10 × 0.5
                          … 上がりは走破タイムに含まれるため重みは半分
       + 負担重量スコア : (当該馬の負担重量 - 出走馬平均負担重量) × 2  … 1kg = 2点
                          … 重い斤量で走った馬を高く評価する

コース・距離・馬場が異なるレース同士の直接比較には、コースごとの基準タイムが
必要になるため、現段階では「同じレース内での相対能力」を表す指数とする。
結果データが蓄積されれば、コース別基準タイムを用いた絶対指数に拡張できる。

あわせて「妙味ギャップ」= オッズ順位 - 指数順位 を出す。
プラスが大きいほど、市場（オッズ）に対して指数が高く、過小評価の候補。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "results"
OUT_DIR = ROOT / "data" / "index"


def parse_time(t):
    if not t:
        return None
    m = re.fullmatch(r"(?:(\d+):)?(\d+(?:\.\d+)?)", t.strip())
    if not m:
        return None
    return (int(m.group(1)) * 60 if m.group(1) else 0) + float(m.group(2))


def compute_race(data):
    runners = []
    for r in data["runners"]:
        sec = parse_time(r.get("time"))
        if sec is None or r.get("last3f") is None or r.get("burden") is None:
            continue  # 中止・除外などタイムがない馬は指数対象外
        runners.append({**r, "_sec": sec})
    if not runners:
        return []
    avg_time = sum(r["_sec"] for r in runners) / len(runners)
    avg_3f = sum(r["last3f"] for r in runners) / len(runners)
    avg_burden = sum(r["burden"] for r in runners) / len(runners)
    for r in runners:
        time_score = (avg_time - r["_sec"]) * 10
        f3_score = (avg_3f - r["last3f"]) * 10 * 0.5
        burden_score = (r["burden"] - avg_burden) * 2
        r["index"] = round(100 + time_score + f3_score + burden_score, 1)
        r["index_parts"] = {
            "time": round(time_score, 1),
            "last3f": round(f3_score, 1),
            "burden": round(burden_score, 1),
        }
    runners.sort(key=lambda x: -x["index"])
    for i, r in enumerate(runners, 1):
        r["index_rank"] = i
    by_odds = sorted(runners, key=lambda x: (x["win_odds"] is None, x["win_odds"] or 0))
    for i, r in enumerate(by_odds, 1):
        r["odds_rank"] = i
    for r in runners:
        r["value_gap"] = r["odds_rank"] - r["index_rank"]
    return [
        {
            "rank": r["rank"],
            "number": r["number"],
            "name": r["name"],
            "jockey": r["jockey"],
            "time": r["time"],
            "last3f": r["last3f"],
            "burden": r["burden"],
            "popularity": r["popularity"],
            "win_odds": r["win_odds"],
            "index": r["index"],
            "index_rank": r["index_rank"],
            "odds_rank": r["odds_rank"],
            "value_gap": r["value_gap"],
            "index_parts": r["index_parts"],
        }
        for r in sorted(runners, key=lambda x: x["index_rank"])
    ]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    races = []
    for fp in sorted(RESULTS_DIR.glob("*.json")):
        if fp.name == "index.json":
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        scored = compute_race(data)
        races.append({
            "race_id": data["race_id"],
            "race_name": data["race_name"],
            "date": data["date"],
            "track": data["track"],
            "race_number": data["race_number"],
            "course": data.get("course"),
            "going": data.get("going"),
            "runners": scored,
        })
        print(f"== {data['date']} {data['race_name']}（{data['track']} {data.get('course')}・{data.get('going')}）")
        for r in scored:
            print(f"  指数{r['index_rank']:>2}位 {r['index']:>6}  {r['number']:>2} {r['name']} "
                  f"（{r['rank']}着 / {r['popularity']}番人気 {r['win_odds']}倍 / 妙味ギャップ {r['value_gap']:+d}）")
    races.sort(key=lambda x: x["date"])
    out = OUT_DIR / "ability_index.json"
    out.write_text(json.dumps({"version": "0.1", "races": races}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
