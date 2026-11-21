#!/usr/bin/env python3
"""netkeibaの出馬表ページを取得し、data/entries/<race_id>.json に保存する。

使い方: python3 scripts/fetch_entry.py <race_id>
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
OUT_DIR = ROOT / "data" / "entries"
JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (personal keiba analysis; low frequency)"}
# netkeibaの略称表記を正式名称に寄せる（登録データとの照合のため）
RACE_NAME_ALIASES = {"マイルＣＳ": "マイルチャンピオンシップ", "マイルCS": "マイルチャンピオンシップ"}


def normalize_race_name(name: str) -> str:
    return RACE_NAME_ALIASES.get(name, name)


def parse_entry(race_id: str) -> dict:
    url = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}"
    res = requests.get(url, headers=UA, timeout=30)
    res.raise_for_status()
    res.encoding = "utf-8"
    soup = BeautifulSoup(res.text, "html.parser")

    title = soup.title.get_text() if soup.title else ""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\S+?)(\d+)R", title)
    race_name = normalize_race_name(re.sub(r"\(.*?\)$", "", title.split(" ")[0].strip())) if title else ""
    date = track = race_number = None
    if m:
        date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        track = m.group(4)
        race_number = int(m.group(5))

    course = None
    rd = soup.select_one(".RaceData01")
    if rd:
        t = rd.get_text(" ", strip=True)
        cm = re.search(r"(芝|ダート|障害)\s*(\d+)\s*m", t)
        if cm:
            course = f"{cm.group(1)}{cm.group(2)}m"

    table = soup.select_one("table.ShutubaTable") or soup.select_one("table.RaceTable01") or soup.find("table")
    if table is None:
        raise RuntimeError("出馬表テーブルが見つかりませんでした")
    trs = table.select("tr")
    headers = [c.get_text(strip=True) for c in trs[0].select("th,td")]
    def col(*names):
        for i, h in enumerate(headers):
            if any(n in h for n in names):
                return i
        return None
    c_num = col("馬番")
    c_name = col("馬名")
    c_jockey = col("騎手")
    c_burden = col("斤量")
    c_odds = col("オッズ")
    c_pop = col("人気")
    c_bracket = col("枠")
    if c_num is None or c_name is None:
        raise RuntimeError(f"列を特定できませんでした: {headers}")

    runners = []
    for tr in trs[1:]:
        td = [c.get_text(strip=True) for c in tr.select("td")]
        if len(td) <= max(c_num, c_name):
            continue
        if not td[c_num].isdigit():
            continue
        runners.append({
            "bracket": int(td[c_bracket]) if c_bracket is not None and td[c_bracket].isdigit() else None,
            "number": int(td[c_num]),
            "name": td[c_name],
            "burden": float(td[c_burden]) if c_burden is not None and re.fullmatch(r"[\d.]+", td[c_burden] or "") else None,
            "jockey": td[c_jockey] if c_jockey is not None else "",
            "win_odds": float(td[c_odds]) if c_odds is not None and re.fullmatch(r"[\d.]+", td[c_odds] or "") else None,
            "popularity": int(td[c_pop]) if c_pop is not None and td[c_pop].isdigit() else None,
        })
    if not runners:
        raise RuntimeError("出走馬データを読み取れませんでした")
    runners.sort(key=lambda r: r["number"])

    return {
        "race_id": race_id,
        "race_name": race_name,
        "date": date,
        "track": track,
        "race_number": race_number,
        "course": course,
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
        sys.exit("使い方: python3 scripts/fetch_entry.py <race_id (12桁)>")
    race_id = sys.argv[1]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = parse_entry(race_id)
    out = OUT_DIR / f"{race_id}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    rebuild_index()
    print(f"saved {out} ({data['race_name']} / {len(data['runners'])}頭)")


if __name__ == "__main__":
    main()
