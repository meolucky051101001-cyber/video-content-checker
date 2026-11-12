Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Projects\video-content-checker"

' Ghi log ra TEMP de khong lo file log plaintext trong thu muc project.
' Cua so cmd an (window style 0).
WshShell.Run "cmd /c python -m streamlit run app.py --server.headless true --server.port 8501 > ""%TEMP%\vcc_streamlit.log"" 2>&1", 0, False