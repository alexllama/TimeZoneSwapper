; tz_swap_hotkey.ahk  (AutoHotkey v2)
; Ctrl+Alt+T will:
;  - copy selected text (no-op if nothing selected)
;  - run Python script which reads clipboard and writes converted text back to clipboard
;  - reactivate original window and paste over the selection
;  - restore the user's original clipboard contents

; -------- CONFIG: update these paths --------
pythonPath := "C:\Users\alex.llama\AppData\Local\Programs\Python\Python313\python.exe"
scriptPath := "C:\ALlama\TimeZoneSwapper.py"
; --------------------------------------------

; Optional: set to true to keep a log in %TEMP%\tz_swap_ahk.log
enableLog := false
logPath := A_Temp "\tz_swap_ahk.log"

Log(msg) {
    global enableLog, logPath
    if !enableLog
        return
    ts := FormatTime(A_Now, "yyyy-MM-dd HH:mm:ss")
    FileAppend(ts " | " msg "`n", logPath, "UTF-8")
}

CopyWithSentinel(timeoutMs := 1200) {
    ; Returns copied text, or "" if clipboard never changes away from sentinel.
    sentinel := "__TZSWAP_SENTINEL__" A_TickCount "__"
    A_Clipboard := sentinel
    Sleep 30

    start := A_TickCount
    while (A_TickCount - start) < timeoutMs {
        if (A_Clipboard != sentinel) {
            return A_Clipboard
        }
        Sleep 10
    }
    return ""
}

TryCopy_CtrlC(timeoutMs := 1200) {
    ; Try explicit Ctrl down/up to avoid typing "c"
    sentinel := "__TZSWAP_SENTINEL__" A_TickCount "__"
    A_Clipboard := sentinel
    Sleep 30

    Send("{Ctrl down}c{Ctrl up}")
    Log("Copy attempt: Ctrl+C down/up")

    start := A_TickCount
    while (A_TickCount - start) < timeoutMs {
        if (A_Clipboard != sentinel) {
            return A_Clipboard
        }
        Sleep 10
    }
    return ""
}

TryCopy_ContextMenu(timeoutMs := 1500) {
    ; For Chromium/webview selections (Obsidian preview): Shift+F10 opens context menu, then 'c' triggers Copy.
    sentinel := "__TZSWAP_SENTINEL__" A_TickCount "__"
    A_Clipboard := sentinel
    Sleep 30

    ; Open context menu at selection
    Send("+{F10}")
    Sleep 120
    ; Choose Copy (usually 'c' is the mnemonic)
    Send("c")
    Log("Copy attempt: context menu (+F10 then c)")

    start := A_TickCount
    while (A_TickCount - start) < timeoutMs {
        if (A_Clipboard != sentinel) {
            return A_Clipboard
        }
        Sleep 10
    }
    return ""
}

CopySelectionOrEmpty(winHwnd) {
    ; Return selection text or "".
    WinActivate(winHwnd)
    WinWaitActive(winHwnd, 1)
    Sleep 80

    ; Determine process name (for Obsidian-specific fallback)
    proc := ""
    try proc := WinGetProcessName("ahk_id " winHwnd)
    Log("Active process: " proc)

    ; First try Ctrl+C (works in Teams, editors, etc.)
    t := TryCopy_CtrlC(900)
    if (t != "") {
        Log("Copy success via Ctrl+C")
        return t
    }

    ; If Ctrl+C failed, and we're in Obsidian, try context-menu copy (preview-friendly)
    if (InStr(StrLower(proc), "obsidian")) {
        t := TryCopy_ContextMenu(1600)
        if (t != "") {
            Log("Copy success via context menu")
            return t
        }
    }

    ; Last fallback: Ctrl+Insert (sometimes works in odd controls)
    sentinel := "__TZSWAP_SENTINEL__" A_TickCount "__"
    A_Clipboard := sentinel
    Sleep 30
    Send("{Ctrl down}{Insert}{Ctrl up}")
    Log("Copy attempt: Ctrl+Insert fallback")

    start := A_TickCount
    while (A_TickCount - start) < 900 {
        if (A_Clipboard != sentinel) {
            Log("Copy success via Ctrl+Insert")
            return A_Clipboard
        }
        Sleep 10
    }

    return ""
}

^!t:: {
    Log("Hotkey fired")

    origWin := WinExist("A")
    Log("origWin HWND=" origWin)

    ; Release modifiers so we don't confuse the target app
    KeyWait("Ctrl")
    KeyWait("Alt")
    Sleep 40

    clipSaved := ClipboardAll()
    Log("Saved clipboard")

    if (!origWin) {
        Log("No active window -> exit")
        A_Clipboard := clipSaved
        return
    }

    selText := CopySelectionOrEmpty(origWin)
    Log("Copied selection: " SubStr(selText, 1, 200))

    if (selText = "") {
        Log("No selection copied -> exiting")
        A_Clipboard := clipSaved
        return
    }

    ; Put selection on clipboard for Python explicitly
    A_Clipboard := selText
    Sleep 30

    cmd := '"' pythonPath '" "' scriptPath '"'
    Log("Running: " cmd)

    try {
        RunWait(cmd, "", "Hide")
        Log("Python exited")
    } catch as e {
        Log("RunWait failed: " e.Message)
        A_Clipboard := clipSaved
        return
    }

    ; Wait for converter to update clipboard to something else
    start := A_TickCount
    while (A_TickCount - start) < 3000 {
        if (A_Clipboard != selText && A_Clipboard != "") {
            break
        }
        Sleep 10
    }

    converted := A_Clipboard
    Log("Clipboard after python: " SubStr(converted, 1, 300))

    if (converted = "" || converted = selText) {
        Log("Converter did not update clipboard -> exiting")
        A_Clipboard := clipSaved
        return
    }

    WinActivate(origWin)
    WinWaitActive(origWin, 1)
    Sleep 60

    Send("^v")
    Log("Sent Ctrl+V (paste)")
    Sleep 80

    A_Clipboard := clipSaved
    Sleep 40
    Log("Restored clipboard")
}