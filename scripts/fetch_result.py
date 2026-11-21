#!/usr/bin/env python3
"""netkeibaのレース結果ページを取得し、data/results/<race_id>.json に保存する。

使い方: python3 scripts/fetch_result.py <race_id>
個人利用の範囲で、1回の実行につき対象ページへのアクセスは1回だけにしています。
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "results"
JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (personal keiba analysis; low frequency)"}


def parse_result(race_id: str) -> dict:
    url = f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    res = requests.get(url, headers=UA, timeout=30)
    res.raise_for_status()
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    # レース名・日付・競馬場・レース番号はタイトルから取る
    # 例: 福島記念 結果・払戻 | 2026年11月21日 福島11R レース情報(JRA) - netkeiba
    title = soup.title.get_text() if soup.title else ""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\S+?)(\d+)R", title)
    race_name = re.sub(r"\(.*?\)$", "", title.split(" ")[0].strip()) if title else ""
    date = track = race_number = None
    if m:
        date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        track = m.group(4)
        race_number = int(m.group(5))

    # コース・天候・馬場（RaceData01: 15:20発走 / 芝2000m (右 B) / 天候:曇 / 馬場:重）
    course = weather = going = None
    rd = soup.select_one(".RaceData01")
    if rd:
        t = rd.get_text(" ", strip=True)
        cm = re.search(r"(芝|ダート|障害)\s*(\d+)\s*m", t)
        if cm:
            course = f"{cm.group(1)}{cm.group(2)}m"
        wm = re.search(r"天候[:：]\s*(\S+)", t)
        if wm:
            weather = wm.group(1)
        gm = re.search(r"馬場[:：]\s*(\S+)", t)
        if gm:
            going = gm.group(1)
        else:
            # 結果ページでは「/ 稍 /」のように馬場だけが単独表記される
            gm2 = re.search(r"/\s*(良|稍重|稍|重|不良)\s*(?:/|$)", t)
            if gm2:
                going = gm2.group(1)

    table = soup.select_one("table.RaceTable01") or soup.find("table")
    if table is None:
        raise RuntimeError("結果テーブルが見つかりませんでした")
    runners = []
    for tr in table.select("tr")[1:]:
        td = [c.get_text(strip=True) for c in tr.select("td")]
        if len(td) < 12:
            continue
        rank_text = td[0]
        rank = int(rank_text) if rank_text.isdigit() else None
        runners.append({
            "rank": rank,
            "status": None if rank is not None else rank_text,  # 取消・除外・中止など
            "bracket": int(td[1]) if td[1].isdigit() else None,
            "number": int(td[2]) if td[2].isdigit() else None,
            "name": td[3],
            "burden": float(td[5]) if re.fullmatch(r"[\d.]+", td[5] or "") else None,
            "jockey": td[6],
            "time": td[7] or None,
            "popularity": int(td[9]) if td[9].isdigit() else None,
            "win_odds": float(td[10]) if re.fullmatch(r"[\d.]+", td[10] or "") else None,
            "last3f": float(td[11]) if re.fullmatch(r"[\d.]+", td[11] or "") else None,
        })
    if not runners:
        raise RuntimeError("出走馬データを読み取れませんでした")

    return {
        "race_id": race_id,
        "race_name": race_name,
        "date": date,
        "track": track,
        "race_number": race_number,
        "course": course,
        "weather": weather,
        "going": going,
        "source": url,
        "fetched_at": datetime.now(JST).isoformat(timespec="seconds"),
        "runners": runners,
    }


def rebuild_index() -> None:
    items = []
    for p in sorted(OUT_DIR.glob("*.json")):
        if p.name == "index.json":
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        items.append({
            "race_id": d["race_id"],
            "race_name": d["race_name"],
            "date": d["date"],
            "track": d["track"],
            "race_number": d["race_number"],
        })
    items.sort(key=lambda x: (x["date"] or "", x["race_id"]), reverse=True)
    (OUT_DIR / "index.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d{12}", sys.argv[1]):
        sys.exit("使い方: python3 scripts/fetch_result.py <race_id (12桁)>")
    race_id = sys.argv[1]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = parse_result(race_id)
    out = OUT_DIR / f"{race_id}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    rebuild_index()
    print(f"saved {out} ({data['race_name']} / {len(data['runners'])}頭)")


if __name__ == "__main__":
    main()
