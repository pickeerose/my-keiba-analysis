#!/usr/bin/env python3
"""出馬表の各馬について、直近5走（JRA）の結果を取りに行く。

netkeiba の出馬表ページから馬IDを引き、db.netkeiba の馬別成績ページで
対象レースより前のレースIDを新しい順に集め、未取得のものは結果JSONとして
data/results/ に保存する。これにより build_entry_index.py が「ある分だけ」
ではなく本当の近5走平均を付けられるようになる。

使い方: python3 scripts/fetch_history5.py <race_id> [--count 5]

- 取得は低頻度（リクエスト間隔 2 秒）。
- 403/404 等で取れないレースはスキップし、次候補（最大8走前まで）で埋める。
- 外国馬の海外レースは race.netkeiba に結果ページがなく自動でスキップされる。
- 最後に結果インデックスと能力指数 v0.2 を再計算する。
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_result import parse_result, rebuild_index  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "results"
ENTRIES_DIR = ROOT / "data" / "entries"
SLEEP = 2.0
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "ja,en;q=0.8"}
DB_UA = dict(UA)


def get_shutuba_map(session, race_id):
    """出馬表ページから {馬名: 馬ID} を作る。"""
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    res = session.get(url, headers=UA, timeout=30)
    res.raise_for_status()
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")
    mapping = {}
    for a in soup.find_all("a", href=re.compile(r"/horse/\d{10}")):
        hid = re.search(r"/horse/(\d{10})", a["href"]).group(1)
        name = a.get_text(strip=True)
        if name:
            mapping[name] = hid
    return mapping


def get_history_candidates(session, horse_id, target_date, limit=8):
    """馬別成績ページから target_date より前のレースIDを新しい順に返す。"""
    top = f"https://db.netkeiba.com/horse/{horse_id}/"
    last_err = None
    res = None
    for attempt in range(2):  # タイムアウト時はウォームアップから1回だけ再試行
        try:
            session.get(top, headers=DB_UA, timeout=60)  # ウォームアップ（これがないと result が 403）
            time.sleep(SLEEP)
            hdr = dict(DB_UA)
            hdr["Referer"] = top
            res = session.get(f"https://db.netkeiba.com/horse/result/{horse_id}/",
                              headers=hdr, timeout=60)
            res.raise_for_status()
            break
        except Exception as e:
            last_err = e
            res = None
            time.sleep(SLEEP * 2)
    if res is None:
        raise last_err
    res.encoding = "EUC-JP"
    soup = BeautifulSoup(res.text, "html.parser")
    tbl = soup.find("table", class_="db_h_race_results")
    out = []
    if not tbl:
        return out
    for tr in tbl.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if not tds:
            continue
        date_txt = tds[0].get_text(strip=True).replace("/", "-")
        a = tr.find("a", href=re.compile(r"/race/\d{12}"))
        if not a:
            continue
        rid = re.search(r"/race/(\d{12})", a["href"]).group(1)
        if date_txt < target_date:
            out.append(rid)
        if len(out) >= limit:
            break
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    count = 5
    if "--count" in sys.argv:
        count = int(sys.argv[sys.argv.index("--count") + 1])
    if len(args) != 1:
        sys.exit("使い方: python3 scripts/fetch_history5.py <race_id> [--count 5]")
    race_id = args[0]
    entry_path = ENTRIES_DIR / f"{race_id}.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8"))
    target_date = entry.get("date")
    if not target_date:
        idx = json.loads((ENTRIES_DIR / "index.json").read_text(encoding="utf-8"))
        target_date = next(i["date"] for i in idx if i["race_id"] == race_id)
    runners = entry.get("runners") or entry.get("horses") or []
    names = [r["name"] for r in runners]
    print(f"対象: {entry.get('race_name')}（{target_date}） {len(names)}頭 / 直近{count}走")

    session = requests.Session()
    shutuba = get_shutuba_map(session, race_id)
    print(f"馬ID取得: {len(shutuba)}頭")
    time.sleep(SLEEP)

    have = {p.stem for p in RESULTS_DIR.glob("*.json")} - {"index"}
    fetched, failed = [], []
    for name in names:
        hid = shutuba.get(name)
        if not hid:
            print(f"  {name}: 馬IDなし（スキップ）")
            continue
        try:
            cands = get_history_candidates(session, hid, target_date, limit=count + 3)
        except Exception as e:
            print(f"  {name}: 成績ページ取得失敗 ({e})")
            time.sleep(SLEEP)
            continue
        time.sleep(SLEEP)
        secured = 0
        for rid in cands:
            if secured >= count:
                break
            if rid in have:
                secured += 1
                continue
            try:
                data = parse_result(rid)
                (RESULTS_DIR / f"{rid}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                have.add(rid)
                fetched.append(rid)
                secured += 1
                print(f"  {name}: 取得 {rid} {data.get('race_name')}（{secured}/{count}）")
            except Exception as e:
                failed.append(rid)
                print(f"  {name}: {rid} 取得失敗 ({e})")
            time.sleep(SLEEP)
        print(f"  {name}: 直近{secured}走分を確保")

    rebuild_index()
    print(f"新規取得 {len(fetched)} レース / 失敗 {len(failed)}")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "ability_index_v02.py")],
                   check=False, capture_output=True)
    print("能力指数 v0.2 を再計算しました")


if __name__ == "__main__":
    main()
