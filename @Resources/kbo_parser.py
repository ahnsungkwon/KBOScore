# -*- coding: utf-8 -*-
"""
KBO Score Parser for Rainmeter (v1.6)
- offset을 dayoffset.txt 파일로 영구 저장 (Rainmeter !WriteKeyValue 회피)
- 명령행 인자 동작:
    python kbo_parser.py          : 현재 저장된 offset 사용
    python kbo_parser.py 0        : offset=0 (오늘로 리셋)
    python kbo_parser.py +1       : 현재 offset + 1
    python kbo_parser.py -1       : 현재 offset - 1
    python kbo_parser.py =5       : offset을 5로 설정 (절대값)
출력 인코딩: UTF-16 LE with BOM
데이터 출처: koreabaseball.com (모든 권리는 KBO에 있음)
"""
import re
import os
import sys
import tempfile
import html as html_lib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, date, timedelta, time as dtime

URL = "https://www.koreabaseball.com/Schedule/ScoreBoard.aspx"
RANK_URL = "https://www.koreabaseball.com/Record/TeamRank/TeamRankDaily.aspx"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REQUEST_TIMEOUT = 12
MAX_GAMES = 5

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "kbo_data.inc")
LOG_FILE = os.path.join(SCRIPT_DIR, "kbo_parser.log")
OFFSET_FILE = os.path.join(SCRIPT_DIR, "dayoffset.txt")

TEAM_CODE_MAP = {
    "KT": "KT", "OB": "두산", "LG": "LG", "LT": "롯데",
    "SS": "삼성", "SK": "SSG", "HH": "한화", "NC": "NC",
    "HT": "KIA", "WO": "키움",
}
WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]
WEEKDAY_KR_FULL = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
WEEKDAY_EN_UPPER = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
MONTH_EN_UPPER = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
]
TEAM_FULL_NAME_MAP = {
    "KT": "KT 위즈",
    "두산": "두산 베어스",
    "LG": "LG 트윈스",
    "롯데": "롯데 자이언츠",
    "삼성": "삼성 라이온즈",
    "SSG": "SSG 랜더스",
    "한화": "한화 이글스",
    "NC": "NC 다이노스",
    "KIA": "KIA 타이거즈",
    "키움": "키움 히어로즈",
}
TEAM_POSTER_NAME_MAP = {
    "KT": "KT",
    "두산": "DOOSAN",
    "LG": "LG",
    "롯데": "LOTTE",
    "삼성": "SAMSUNG",
    "SSG": "SSG",
    "한화": "HANWHA",
    "NC": "NC",
    "KIA": "KIA",
    "키움": "KIWOOM",
}


def log(msg):
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 100 * 1024:
            open(LOG_FILE, "w").close()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def configure_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def read_saved_offset():
    """저장된 offset 읽기 (파일 없거나 오류 시 0)."""
    try:
        if os.path.exists(OFFSET_FILE):
            with open(OFFSET_FILE, "r", encoding="utf-8") as f:
                return int(f.read().strip())
    except Exception:
        pass
    return 0


def save_offset(value):
    try:
        with open(OFFSET_FILE, "w", encoding="utf-8") as f:
            f.write(str(value))
    except Exception as e:
        log(f"save_offset error: {e}")


def resolve_offset():
    """
    명령행 인자를 해석해서 최종 offset 결정.
    인자 형식:
      없음            → 저장된 값 그대로
      '0' / '5' / '-3' → 절대값 (= 모드)
      '+1' / '-1'      → 상대값 (현재값에 가감)
      '=5'             → 절대값 5
    """
    saved = read_saved_offset()
    if len(sys.argv) < 2:
        return saved

    arg = sys.argv[1].strip()
    if not arg:
        return saved

    # 명시적 절대값 '=N'
    if arg.startswith("="):
        try:
            new_val = int(arg[1:])
            save_offset(new_val)
            return new_val
        except ValueError:
            return saved

    # 상대값: '+1', '-1', '+2' 등 (부호로 시작)
    if arg[0] in ("+", "-") and len(arg) > 1 and arg[1:].lstrip("+-").isdigit():
        # '+1' 처럼 부호+숫자면 상대
        # 단, '-1'은 절대값 -1로 해석될 수 있어 명시적 구분 필요
        # 규약: 정수만 있으면 절대값, '+N'/'-N' 형태도 절대값
        # 상대값은 'rel:+1' / 'rel:-1' 같은 prefix 사용 권장 → 단순화 위해 별도 처리
        pass

    # 'rel+1' / 'rel-1' 패턴
    if arg.startswith("rel"):
        try:
            delta = int(arg[3:])
            new_val = saved + delta
            save_offset(new_val)
            return new_val
        except ValueError:
            return saved

    # 그 외 정수는 절대값
    try:
        new_val = int(arg)
        save_offset(new_val)
        return new_val
    except ValueError:
        return saved


def request_html(data=None, url=URL):
    headers = {
        "User-Agent": UA,
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    last_error = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            return urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT).read().decode("utf-8", errors="ignore")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_error = e
            log(f"request retry {attempt + 1}: {e}")
    raise last_error


def extract_form_state(html):
    state = {}
    for name in ["__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"]:
        m = re.search(rf'{name}"\s*value="([^"]*)"', html)
        if m:
            state[name] = m.group(1)
    return state


def get_form_state():
    html = request_html()
    state = extract_form_state(html)
    return state, html


def fetch_for_date(target_date):
    state, html_today = get_form_state()
    m = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', html_today)
    if m:
        current_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if current_date == target_date:
            return html_today

    next_day = target_date + timedelta(days=1)
    hf_date = next_day.strftime("%Y%m%d")
    form = {
        "__EVENTTARGET": "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$btnPreDate",
        "__EVENTARGUMENT": "",
        "__VIEWSTATE": state.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": state.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": state.get("__EVENTVALIDATION", ""),
        "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfSearchDate": hf_date,
    }
    data = urllib.parse.urlencode(form).encode("utf-8")
    return request_html(data=data)


def extract_page_date(html):
    m = re.search(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', html)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def parse_games(html):
    games = []
    seen = set()
    blocks = re.split(r"class=['\"]score_wrap['\"]", html)
    for block in blocks[1:]:
        block = block[:5000]
        emblems = re.findall(r'emblem_([A-Z]+)\.png', block)
        if len(emblems) < 2:
            continue
        away_code, home_code = emblems[0], emblems[1]
        away = TEAM_CODE_MAP.get(away_code, away_code)
        home = TEAM_CODE_MAP.get(home_code, home_code)

        away_m = re.search(r'lblAwayTeamScore_\d+["\']?>([^<]*)</span>', block)
        home_m = re.search(r'lblHomeTeamScore_\d+["\']?>([^<]*)</span>', block)
        away_score = (away_m.group(1).strip() if away_m else "") or "-"
        home_score = (home_m.group(1).strip() if home_m else "") or "-"

        state_m = re.search(r'lblGameState_\d+["\']?>([^<]*)</span>', block)
        status = state_m.group(1).strip() if state_m else ""

        place_m = re.search(
            r"class=['\"]place['\"]>([^<]+?)<span>(\d{1,2}:\d{2})</span>",
            block
        )
        stadium = place_m.group(1).strip() if place_m else ""
        time_str = place_m.group(2).strip() if place_m else ""

        key = (away, home, time_str, stadium)
        if key in seen:
            continue
        seen.add(key)

        games.append({
            "away": away, "home": home,
            "away_score": away_score, "home_score": home_score,
            "status": status, "stadium": stadium, "time": time_str,
        })
    return sorted(games, key=lambda g: (parse_time(g["time"]) is None, parse_time(g["time"]) or dtime.max))


def fetch_rankings_for_date(target_date):
    html = request_html(url=RANK_URL)
    state = extract_form_state(html)
    target = target_date.strftime("%Y%m%d")

    current_m = re.search(r'hfSearchDate[^>]*value=["\'](\d{8})', html)
    if current_m and current_m.group(1) == target:
        return parse_rankings(html)

    form = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": state.get("__VIEWSTATE", ""),
        "__VIEWSTATEGENERATOR": state.get("__VIEWSTATEGENERATOR", ""),
        "__EVENTVALIDATION": state.get("__EVENTVALIDATION", ""),
        "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$txtCanlendar": target + "  ",
        "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfSearchYear": target[:4],
        "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfSearchDate": target,
        "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$hfSearchSeries": "0",
        "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$ddlSeries": "0",
        "ctl00$ctl00$ctl00$cphContents$cphContents$cphContents$btnCalendarSelect": "",
    }
    data = urllib.parse.urlencode(form).encode("utf-8")
    return parse_rankings(request_html(data=data, url=RANK_URL))


def strip_tags(value):
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    value = re.sub(r"<.*?>", "", value)
    return html_lib.unescape(value).strip()


def parse_rankings(html):
    table_m = re.search(r'<table[^>]*summary=["\']순위,\s*팀명.*?</table>', html, re.S)
    if not table_m:
        return {}

    rankings = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table_m.group(0), re.S):
        cells = [strip_tags(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 2 and cells[0].isdigit():
            rankings[cells[1]] = cells[0]
    return rankings


def parse_time(time_str):
    if not time_str:
        return None
    m = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if m:
        try:
            return dtime(int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def is_pre_game(g, target_date, today, now):
    s = g["status"]
    if target_date > today:
        return True
    if s in ("", "경기전"):
        return True
    if target_date == today:
        game_time = parse_time(g["time"])
        if game_time and now.time() < game_time:
            if s in ("1회초", "1회말") and g["away_score"] in ("0", "-") and g["home_score"] in ("0", "-"):
                return True
    return False


def format_game_line(g, target_date, today, now):
    s = g["status"]
    if is_pre_game(g, target_date, today, now):
        display = f"{g['away']} vs {g['home']}"
        if g["time"] and g["stadium"]:
            status_disp = f"{g['time']} {g['stadium']}"
        elif g["time"]:
            status_disp = g["time"]
        else:
            status_disp = "경기전"
        return display, status_disp
    if s == "경기종료":
        return f"{g['away']} {g['away_score']} : {g['home_score']} {g['home']}", "종료"
    if s in ("연기", "취소", "우천", "중단"):
        return f"{g['away']} vs {g['home']}", s
    return f"{g['away']} {g['away_score']} : {g['home_score']} {g['home']}", s or g["stadium"]


def date_label(target_date, today):
    diff = (target_date - today).days
    base = f"{target_date.strftime('%Y.%m.%d')} ({WEEKDAY_KR[target_date.weekday()]})"
    if diff == 0:
        return f"{base} · 오늘"
    elif diff == -1:
        return f"{base} · 어제"
    elif diff == 1:
        return f"{base} · 내일"
    elif diff < 0:
        return f"{base} · {-diff}일 전"
    else:
        return f"{base} · {diff}일 후"


def poster_date_label(target_date):
    month = MONTH_EN_UPPER[target_date.month - 1]
    return f"{WEEKDAY_KR_FULL[target_date.weekday()]} · {month} {target_date.day:02d} {target_date.year}"


def venue_label(games):
    for game in games:
        if game.get("stadium"):
            return game["stadium"]
    return "KBO 리그"


def clean_value(value, max_len=None):
    value = re.sub(r"[\r\n]+", " ", str(value)).strip()
    if max_len and len(value) > max_len:
        return value[:max_len - 1] + "…"
    return value


def game_status_label(g, target_date, today, now):
    if is_pre_game(g, target_date, today, now):
        return g.get("time") or "경기전"
    if g["status"] == "경기종료":
        return "종료"
    if g["status"] in ("연기", "취소", "우천", "중단"):
        return g["status"]
    return g["status"] or (g.get("time") or "")


def score_value(g, key, target_date, today, now):
    if is_pre_game(g, target_date, today, now):
        return "·"
    return clean_value(g.get(key) or "-")


def team_name_with_rank(team, rankings):
    name = TEAM_FULL_NAME_MAP.get(team, team)
    rank = rankings.get(team, "")
    if rank:
        return f"{name} {rank}위"
    return name


def data_keys():
    keys = [
        "UpdateTime", "GameDate", "DayOffset", "GameCount",
        "PosterWeekday", "PosterDate", "PosterVenue",
        "HeroAway", "HeroHome", "HeroStatus",
        "FooterLabel",
        "PrevFill", "PrevTextColor", "TodayFill", "TodayTextColor", "NextFill", "NextTextColor",
    ]
    for i in range(1, MAX_GAMES + 1):
        keys.extend([
            f"Game{i}Display", f"Game{i}Status",
            f"Game{i}Away", f"Game{i}Home",
            f"Game{i}AwayScore", f"Game{i}HomeScore",
        ])
    return keys


def build_data(games, target_date, today, now, day_offset, rankings=None):
    rankings = rankings or {}
    label = date_label(target_date, today)
    active_fill = "30,77,120,255"
    inactive_fill = "238,232,207,248"
    active_text = "255,255,255,255"
    inactive_text = "30,77,120,255"
    data = {
        "UpdateTime": now.strftime("%H:%M"),
        "GameDate": clean_value(label),
        "DayOffset": str(day_offset),
        "GameCount": str(len(games)),
        "PosterWeekday": WEEKDAY_EN_UPPER[target_date.weekday()],
        "PosterDate": poster_date_label(target_date),
        "PosterVenue": venue_label(games),
        "HeroAway": TEAM_POSTER_NAME_MAP.get(games[0]["away"], games[0]["away"]) if games else "KBO",
        "HeroHome": TEAM_POSTER_NAME_MAP.get(games[0]["home"], games[0]["home"]) if games else "BASEBALL",
        "HeroStatus": game_status_label(games[0], target_date, today, now) if games else "NO GAME",
        "FooterLabel": "TONIGHT" if day_offset == 0 else ("TOMORROW" if day_offset == 1 else ("UPCOMING" if day_offset > 1 else "PAST")),
        "PrevFill": active_fill if day_offset < 0 else inactive_fill,
        "PrevTextColor": active_text if day_offset < 0 else inactive_text,
        "TodayFill": active_fill if day_offset == 0 else inactive_fill,
        "TodayTextColor": active_text if day_offset == 0 else inactive_text,
        "NextFill": active_fill if day_offset > 0 else inactive_fill,
        "NextTextColor": active_text if day_offset > 0 else inactive_text,
    }
    if len(games) == 0:
        data["Game1Display"] = "경기가 없습니다"
        data["Game1Status"] = "휴식일"
        start = 2
    else:
        start = 1

    for i in range(start - 1, MAX_GAMES):
        idx = i + 1
        if i < len(games) and len(games) != 0:
            game = games[i]
            display, status_disp = format_game_line(games[i], target_date, today, now)
            data[f"Game{idx}Display"] = clean_value(display, 34)
            data[f"Game{idx}Status"] = clean_value(status_disp, 18)
            data[f"Game{idx}Away"] = clean_value(team_name_with_rank(game["away"], rankings), 14)
            data[f"Game{idx}Home"] = clean_value(team_name_with_rank(game["home"], rankings), 14)
            data[f"Game{idx}AwayScore"] = score_value(game, "away_score", target_date, today, now)
            data[f"Game{idx}HomeScore"] = score_value(game, "home_score", target_date, today, now)
        else:
            data[f"Game{idx}Display"] = data.get(f"Game{idx}Display", "")
            data[f"Game{idx}Status"] = data.get(f"Game{idx}Status", "")
            data[f"Game{idx}Away"] = data.get(f"Game{idx}Away", "")
            data[f"Game{idx}Home"] = data.get(f"Game{idx}Home", "")
            data[f"Game{idx}AwayScore"] = data.get(f"Game{idx}AwayScore", "")
            data[f"Game{idx}HomeScore"] = data.get(f"Game{idx}HomeScore", "")
    return data


def build_inc_content(data):
    lines = ["[Variables]"]
    lines.extend(f"{key}={data.get(key, '')}" for key in data_keys())
    return "\r\n".join(lines) + "\r\n"


def write_utf16_bom(path, content):
    fd, tmp_path = tempfile.mkstemp(prefix="kbo_data_", suffix=".tmp", dir=SCRIPT_DIR)
    with os.fdopen(fd, "wb") as f:
        f.write(b"\xff\xfe")
        f.write(content.encode("utf-16-le"))
    os.replace(tmp_path, path)


def rainmeter_quote(value):
    return str(value).replace('"', "'").replace("[", "(").replace("]", ")")


def build_rainmeter_bangs(data):
    bangs = []
    for key in data_keys():
        bangs.append(f'[!SetVariable "{key}" "{rainmeter_quote(data.get(key, ""))}"]')
    bangs.append("[!UpdateMeter *]")
    bangs.append("[!Redraw]")
    return "".join(bangs)


def write_error_inc(msg, day_offset):
    now = datetime.now()
    today = date.today()
    target = today + timedelta(days=day_offset)
    label = date_label(target, today)
    data = {
        "UpdateTime": now.strftime("%H:%M"),
        "GameDate": clean_value(label),
        "DayOffset": str(day_offset),
        "GameCount": "0",
        "PosterWeekday": WEEKDAY_EN_UPPER[target.weekday()],
        "PosterDate": poster_date_label(target),
        "PosterVenue": "KBO 리그",
        "HeroAway": "KBO",
        "HeroHome": "BASEBALL",
        "HeroStatus": "ERROR",
        "FooterLabel": "TONIGHT",
        "PrevFill": "238,232,207,248",
        "PrevTextColor": "30,77,120,255",
        "TodayFill": "30,77,120,255",
        "TodayTextColor": "255,255,255,255",
        "NextFill": "238,232,207,248",
        "NextTextColor": "30,77,120,255",
        "Game1Display": "데이터 오류",
        "Game1Status": clean_value(msg, 30),
        "Game1Away": "데이터 오류",
        "Game1Home": "",
        "Game1AwayScore": "",
        "Game1HomeScore": "",
    }
    for i in range(2, 6):
        data[f"Game{i}Display"] = ""
        data[f"Game{i}Status"] = ""
        data[f"Game{i}Away"] = ""
        data[f"Game{i}Home"] = ""
        data[f"Game{i}AwayScore"] = ""
        data[f"Game{i}HomeScore"] = ""
    write_utf16_bom(OUTPUT_FILE, build_inc_content(data))
    return data


def main():
    configure_stdout()
    arg = sys.argv[1] if len(sys.argv) > 1 else "(none)"
    day_offset = resolve_offset()
    today = date.today()
    target_date = today + timedelta(days=day_offset)
    now = datetime.now()

    try:
        html = fetch_for_date(target_date)
        page_date = extract_page_date(html)
        if page_date != target_date:
            log(f"WARN: arg='{arg}' resolved={day_offset} target={target_date} but page={page_date}")
            games = []
        else:
            games = parse_games(html)

        try:
            rankings = fetch_rankings_for_date(target_date)
        except Exception as rank_error:
            rankings = {}
            log(f"WARN: ranking fetch failed target={target_date}: {rank_error}")

        data = build_data(games, target_date, today, now, day_offset, rankings)
        content = build_inc_content(data)
        write_utf16_bom(OUTPUT_FILE, content)
        log(f"OK: arg='{arg}' offset={day_offset} target={target_date} games={len(games)}")
        print(build_rainmeter_bangs(data), end="")
    except Exception as e:
        log(f"ERROR arg='{arg}' offset={day_offset}: {e}")
        data = write_error_inc(str(e), day_offset)
        print(build_rainmeter_bangs(data), end="")


if __name__ == "__main__":
    main()
