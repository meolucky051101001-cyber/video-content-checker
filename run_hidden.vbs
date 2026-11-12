Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Projects\video-content-checker"

' Chay hoan toan an bang pythonw. run_tool.pyw tu kiem tra suc khoe server
' (/_stcore/health) roi moi khoi dong neu chua chay, va mo trinh duyet.
WshShell.Run "pythonw run_tool.pyw", 0, False