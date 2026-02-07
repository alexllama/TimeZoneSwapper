#!/usr/bin/env python3
"""
tz_swap_et_awst.py

Hotkey-friendly clipboard time converter between:
- America/New_York (ET: EST/EDT)
- Australia/Perth (AWST)

Behavior:
- Input comes from argv if provided; otherwise reads Windows clipboard.
- Detects source timezone from text markers:
    - ET / EST / EDT / Eastern / America/New_York  => source is ET, convert to AWST
    - AWST / Perth / Australia/Perth              => source is AWST, convert to ET
  If no marker is present: treats the time as LOCAL machine timezone; if local isn't ET/AWST, defaults to ET.
- Parses:
    - "3:30 PM", "15:30", "3pm", "3 PM"
    - "2026-02-03 8:00 AM"
    - "Mar 4 3:30pm"
    - "today 9am", "tomorrow 9am", "yesterday 9am"
    - "next tuesday 3pm", "this fri 10:30"
- Output written back to clipboard:
    "<original> (<converted in other tz>)"
  where converted format is:
    "3:30pm Fri Feb 13 AWST"  (or "... ET")
  Example:
    "thursday 1pm (2:00am Fri Feb 13 AWST)"

Important:
- On Windows, ZoneInfo needs tzdata. If you see ZoneInfoNotFoundError, install:
    python -m pip install --user tzdata
"""

from __future__ import annotations

import re
import sys
import time as _time
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import ctypes
from ctypes import wintypes

# ----------------------------
# Time zones
# ----------------------------
ET = ZoneInfo("America/New_York")
AWST = ZoneInfo("Australia/Perth")

ET_MARKERS = re.compile(r"\b(Eastern|ET|EST|EDT|America/New_York)\b", re.IGNORECASE)
AWST_MARKERS = re.compile(r"\b(AWST|Perth|Australia/Perth)\b", re.IGNORECASE)

# ----------------------------
# Parsing regex
# ----------------------------
TIME_RE = re.compile(r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm|AM|PM)?")
ISO_DATE_RE = re.compile(r"(?P<iso>\d{4}-\d{2}-\d{2})")
MONTHDAY_RE = re.compile(r"(?P<mon>[A-Za-z]{3,9})\.?\s*(?P<day>\d{1,2})")
RELATIVE_RE = re.compile(r"\b(today|tomorrow|yesterday)\b", re.IGNORECASE)
WEEKDAY_RE = re.compile(
    r"\b(?:(this|next)\s+)?(mon|monday|tue|tues|tuesday|wed|wednesday|thu|thur|thurs|thursday|fri|friday|sat|saturday|sun|sunday)\b",
    re.IGNORECASE,
)

WEEKDAY_MAP = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}

# ----------------------------
# Win32 clipboard (safe + retry; no PowerShell; no focus steal when using pythonw.exe)
# ----------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL


def _open_clipboard_with_retry(retries: int = 30, delay_s: float = 0.01) -> bool:
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        _time.sleep(delay_s)
    return False


def read_clipboard_windows() -> str:
    if not _open_clipboard_with_retry():
        return ""
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p).strip()
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def write_clipboard_windows(text: str) -> None:
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)

    if not _open_clipboard_with_retry():
        return

    try:
        if not user32.EmptyClipboard():
            return

        data = text + "\0"
        size_bytes = len(data) * ctypes.sizeof(wintypes.WCHAR)

        hglob = kernel32.GlobalAlloc(GMEM_MOVEABLE, size_bytes)
        if not hglob:
            return

        p = kernel32.GlobalLock(hglob)
        if not p:
            return

        try:
            ctypes.memmove(p, ctypes.create_unicode_buffer(data), size_bytes)
        finally:
            kernel32.GlobalUnlock(hglob)

        # If SetClipboardData succeeds, Windows owns the memory handle.
        if not user32.SetClipboardData(CF_UNICODETEXT, hglob):
            return

    finally:
        user32.CloseClipboard()


# ----------------------------
# Date helpers
# ----------------------------
def next_weekday(reference: date, target_wd: int, when: str | None) -> date:
    """
    when:
      - 'next' => strictly next week's occurrence (if today is same weekday, +7)
      - 'this' or None => nearest occurrence including today
    """
    ref_wd = reference.weekday()
    days_ahead = (target_wd - ref_wd) % 7
    if when == "next":
        days_ahead = days_ahead if days_ahead != 0 else 7
    return reference + timedelta(days=days_ahead)


def parse_input(raw: str):
    """
    Returns (dt_naive, src_zone_hint) where src_zone_hint is ET/AWST or None.
    dt_naive has no tzinfo; tz assignment happens later.
    """
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None

    # timezone hint from markers
    src_zone = None
    if ET_MARKERS.search(s):
        src_zone = ET
        s = ET_MARKERS.sub("", s)
    elif AWST_MARKERS.search(s):
        src_zone = AWST
        s = AWST_MARKERS.sub("", s)

    s = " ".join(s.split())

    # date parsing
    parsed_date = None

    m_iso = ISO_DATE_RE.search(s)
    if m_iso:
        parsed_date = datetime.fromisoformat(m_iso.group("iso")).date()
        s = s.replace(m_iso.group("iso"), "").strip()

    if not parsed_date:
        m_md = MONTHDAY_RE.search(s)
        if m_md:
            try:
                mon = m_md.group("mon")[:3]
                day = int(m_md.group("day"))
                mon_num = datetime.strptime(mon, "%b").month
                parsed_date = date(date.today().year, mon_num, day)
                s = s.replace(m_md.group(0), "").strip()
            except Exception:
                parsed_date = None

    if not parsed_date:
        m_rel = RELATIVE_RE.search(s)
        if m_rel:
            kw = m_rel.group(1).lower()
            today = date.today()
            if kw == "today":
                parsed_date = today
            elif kw == "tomorrow":
                parsed_date = today + timedelta(days=1)
            else:
                parsed_date = today - timedelta(days=1)
            s = s.replace(m_rel.group(0), "").strip()

    if not parsed_date:
        m_wd = WEEKDAY_RE.search(s)
        if m_wd:
            when = m_wd.group(1).lower() if m_wd.group(1) else None
            wd_token = m_wd.group(2).lower()
            wd_key = None
            for k in WEEKDAY_MAP.keys():
                if wd_token.startswith(k):
                    wd_key = k
                    break
            if wd_key:
                parsed_date = next_weekday(date.today(), WEEKDAY_MAP[wd_key], when)
                s = s.replace(m_wd.group(0), "").strip()

    # time parsing
    m_time = TIME_RE.search(s)
    if not m_time:
        # no time => can't parse
        return None

    hour = int(m_time.group("h"))
    minute = int(m_time.group("m")) if m_time.group("m") else 0
    ampm = m_time.group("ampm")
    if ampm:
        am = ampm.lower()
        if am == "pm" and hour < 12:
            hour += 12
        if am == "am" and hour == 12:
            hour = 0

    if not parsed_date:
        parsed_date = date.today()

    dt_naive = datetime.combine(parsed_date, time(hour, minute))
    return dt_naive, src_zone


def determine_source_and_target(dt_naive: datetime, src_zone_hint: ZoneInfo | None):
    """
    Returns: (dt_source_with_tz, source_zone, target_zone)
    """
    if src_zone_hint is not None:
        source = src_zone_hint
    else:
        # try infer from local tz; default to ET
        local_tz = datetime.now().astimezone().tzinfo
        name = getattr(local_tz, "key", None) or getattr(local_tz, "zone", None) or str(local_tz)
        name = str(name)
        if "New_York" in name or "America/New_York" in name or "Eastern" in name:
            source = ET
        elif "Perth" in name or "Australia/Perth" in name or "AWST" in name:
            source = AWST
        else:
            source = ET

    target = AWST if source is ET else ET
    dt_source = dt_naive.replace(tzinfo=source)
    return dt_source, source, target


def tz_label_for(zone: ZoneInfo) -> str:
    return "AWST" if zone is AWST else "ET"


def format_short_core(dt: datetime, tz_label: str) -> str:
    # "2:00am Fri Feb 13 AWST"
    # Windows strftime doesn't reliably support %-I / %-d; handle both.
    try:
        t = dt.strftime("%-I:%M%p")
        d = dt.strftime("%a %b %-d")
    except Exception:
        t = dt.strftime("%I:%M%p").lstrip("0")
        d = dt.strftime("%a %b %d").replace(" 0", " ")
    return f"{t.lower()} {d} {tz_label}"


def main():
    # prefer argv; if none, read clipboard
    if len(sys.argv) > 1:
        raw = " ".join(sys.argv[1:])
    else:
        raw = read_clipboard_windows()

    if not raw or not raw.strip():
        write_clipboard_windows("[tz] clipboard empty (copy a time first)")
        return

    parsed = parse_input(raw)
    if not parsed:
        write_clipboard_windows("[tz] could not parse (try 'next tuesday 3pm', '3:30 PM', or include 'ET'/'Perth')")
        return

    dt_naive, src_hint = parsed

    try:
        dt_source, src_zone, tgt_zone = determine_source_and_target(dt_naive, src_hint)
        dt_target = dt_source.astimezone(tgt_zone)
    except ZoneInfoNotFoundError:
        write_clipboard_windows("[tz] missing tzdata. Run: python -m pip install --user tzdata")
        return

    converted = format_short_core(dt_target, tz_label_for(tgt_zone))
    out = f"{raw.strip()} ({converted})"
    write_clipboard_windows(out)


if __name__ == "__main__":
    main()