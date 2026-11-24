#!/usr/bin/env python3
"""独自能力指数 v0.2（試作）— 位置取り補正つき

v0.1（タイム＋上がり3F＋負担重量）に、最終コーナーの位置取り補正を加える。
  位置取りスコア = (出走馬の最終コーナー平均位置 - 当該馬の最終コーナー位置) × 0.5
  … 前で運んだ馬を1位置あたり +0.5点、後方から届いた馬を -0.5点。
     重みは小さめの試作値。v0.1は末脚馬を高く・先行して勝った馬を低く見る癖が
     あるため、その偏りを緩和するのが目的。上がり3Fがすでに末脚を評価して
     いるので、補正を大きくすると二重計上になる。

コーナー通過順位は fetch_result.py が結果JSONに保存する
corner_passing / 各馬の final_corner_pos を使う。
コーナーデータがないレースは補正 0（v0.1と同値）で計算する。

出力: data/index/ability_index_v02.json（v0.1の ability_index.json は触らない）
検証はマイルCSと東スポ杯2歳Sで v0.1 と並べて行う。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ability_index import compute_race  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "results"
OUT_DIR = ROOT / "data" / "index"

POSITION_WEIGHT = 0.5  # 1位置あたりの補正（試作値）


def compute_race_v02(data):
    base = compute_race(data)  # v0.1の指数・順位・妙味ギャップ入り
    by_number = {r["number"]: r for r in data["runners"]}
    scored_pos = [r["final_corner_pos"] for r in data["runners"]
                  if r.get("final_corner_pos") is not None]
    avg_pos = sum(scored_pos) / len(scored_pos) if scored_pos else None
    for r in base:
        raw = by_number.get(r["number"], {})
        pos = raw.get("final_corner_pos")
        if pos is None or avg_pos is None:
            p_score = 0.0
        else:
            p_score = round((avg_pos - pos) * POSITION_WEIGHT, 1)
        r["final_corner_pos"] = pos
        r["index_v01"] = r["index"]
        r["index"] = round(r["index"] + p_score, 1)
        r["index_parts"] = {**r["index_parts"], "position": p_score}
    base.sort(key=lambda x: -x["index"])
    for i, r in enumerate(base, 1):
        r["index_rank"] = i
    for r in base:
        r["value_gap"] = r["odds_rank"] - r["index_rank"]
    return base, avg_pos


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    races = []
    for fp in sorted(RESULTS_DIR.glob("*.json")):
        if fp.name == "index.json":
            continue
        data = json.loads(fp.read_text(encoding="utf-8"))
        scored, avg_pos = compute_race_v02(data)
        races.append({
            "race_id": data["race_id"],
            "race_name": data["race_name"],
            "date": data["date"],
            "track": data["track"],
            "race_number": data["race_number"],
            "course": data.get("course"),
            "going": data.get("going"),
            "final_corner": data.get("final_corner"),
            "avg_final_corner_pos": round(avg_pos, 1) if avg_pos else None,
            "runners": scored,
        })
        tag = "補正あり" if avg_pos else "コーナーデータなし・補正0"
        print(f"== {data['date']} {data['race_name']}（{tag}）")
        for r in scored:
            d = r["index"] - r["index_v01"]
            print(f"  指数{r['index_rank']:>2}位 {r['index']:>6}（v0.1 {r['index_v01']:>6}・{d:+.1f}）"
                  f"  {r['number']:>2} {r['name']}（{r['rank']}着 / 4角{r['final_corner_pos']}番手）")
    races.sort(key=lambda x: x["date"])
    out = OUT_DIR / "ability_index_v02.json"
    out.write_text(json.dumps(
        {"version": "0.2", "position_weight": POSITION_WEIGHT, "races": races},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
