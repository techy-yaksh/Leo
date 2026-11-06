Set WshShell = CreateObject("WScript.Shell")

' Force the script to look in your specific LEO folder
WshShell.CurrentDirectory = "C:\Users\HP\Desktop\Yaksh\LEO"

' Run the backend using your specific Anaconda Python installation
WshShell.Run "C:\Users\HP\anaconda3\pythonw.exe leo_backend.py", 0, False