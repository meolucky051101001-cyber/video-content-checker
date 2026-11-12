Set Wsh = CreateObject("WScript.Shell")
Wsh.CurrentDirectory = "C:\Projects\video-content-checker"
Wsh.Run "pythonw -m streamlit run app.py --server.headless true --server.port 8501 --server.address 0.0.0.0", 0, False
