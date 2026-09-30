' ===========================================================================
'  e-hu Campus - Streamlit anti-fraud preview launcher (silent, no console).
'
'  Two ways to use it:
'    * Start menu / Startup folder : double-click or logon -> 25s delay, then
'      start the server and open the browser.
'    * Manual, start right now    : wscript.exe start_preview_autostart.vbs --now
'
'  Port 8501  -  URL http://localhost:8501
'  No admin rights needed. Safe to run repeatedly (single instance).
' ===========================================================================
Option Explicit

Dim shell, fso, appDir, port, pyw, cmd, probe, n, delayMs, arg

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
port = 8501

' ---- delay: 25s at logon, 0s when called with --now ----
delayMs = 25000
For Each arg In WScript.Arguments
    If LCase(Trim(arg)) = "--now" Then delayMs = 0
Next
If delayMs > 0 Then WScript.Sleep delayMs

' ---- single instance: exit quietly if 8501 is already served ----
probe = shell.Run("cmd /c netstat -ano | findstr /r /c:""TCP.*:" & port & ".*LISTENING""", 0, True)
If probe = 0 Then WScript.Quit 0

' ---- find pythonw.exe (no console window); fall back to PATH lookup ----
pyw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Python\bin\pythonw.exe"
If Not fso.FileExists(pyw) Then
    pyw = ""
    Dim exec, lines, i
    Set exec = shell.Exec("cmd /c where pythonw.exe")
    lines = Split(exec.StdOut.ReadAll, vbCrLf)
    For i = 0 To UBound(lines)
        If Len(Trim(lines(i))) > 0 Then
            pyw = Trim(lines(i))
            Exit For
        End If
    Next
End If
If pyw = "" Then WScript.Quit 1

' keep the long command on ONE line - WScript.Shell.Run does not join line continuations
cmd = """" & pyw & """ -m streamlit run ""app.py"" --server.port " & port & " --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false --server.fileWatcherType none"

shell.CurrentDirectory = appDir
shell.Run cmd, 0, False

' ---- wait for the port, then open the default browser ----
For n = 1 To 45
    WScript.Sleep 1000
    If shell.Run("cmd /c netstat -ano | findstr /r /c:""TCP.*:" & port & ".*LISTENING""", 0, True) = 0 Then
        shell.Run "http://localhost:" & port & "/", 1, False
        WScript.Quit 0
    End If
Next
WScript.Quit 1
