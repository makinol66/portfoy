Set WshShell = CreateObject("WScript.Shell")
' BAT dosyasıyla aynı klasörde olduğu varsayılır
WshShell.Run chr(34) & "Baslat.bat" & Chr(34), 0
Set WshShell = Nothing