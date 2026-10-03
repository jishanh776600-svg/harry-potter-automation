Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run chr(34) & scriptDir & "\run_autopilot.bat" & chr(34), 0
Set WshShell = Nothing
