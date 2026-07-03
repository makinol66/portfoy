Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Scriptin bulunduğu klasörü tespit et ve oraya odaklan
strPath = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strPath

' Sihirli komut: python -m streamlit
objShell.Run "cmd /c python -m streamlit run fonlar.py", 0, False