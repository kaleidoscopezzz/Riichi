// Windows-only process containment. No process-name kill and no shell-built commands.
using System;
using System.ComponentModel;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text;

namespace RiichiLauncher {
    public sealed class Identity {
        public int ProcessId;
        public string CreationTime;
        public string ImagePath;
    }
    public sealed class ProcessJob : IDisposable {
        [StructLayout(LayoutKind.Sequential)] struct BasicLimits {
            public long PerProcess, PerJob;
            public uint Flags;
            public UIntPtr MinWorkingSet, MaxWorkingSet;
            public uint ActiveProcessLimit;
            public UIntPtr Affinity;
            public uint Priority, Scheduling;
        }
        [StructLayout(LayoutKind.Sequential)] struct IoCounters {
            public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
        }
        [StructLayout(LayoutKind.Sequential)] struct ExtendedLimits {
            public BasicLimits Basic; public IoCounters Io;
            public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
        }
        [StructLayout(LayoutKind.Sequential)] struct SecurityAttributes {
            public int Length; public IntPtr Descriptor;
            [MarshalAs(UnmanagedType.Bool)] public bool Inherit;
        }
        [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] struct StartupInfo {
            public int Size; public string Reserved, Desktop, Title;
            public uint X,Y,XSize,YSize,XChars,YChars,Fill,Flags;
            public short ShowWindow, ReservedSize;
            public IntPtr ReservedBytes, Input, Output, Error;
        }
        [StructLayout(LayoutKind.Sequential)] struct ProcessInfo {
            public IntPtr Process, Thread; public uint ProcessId, ThreadId;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateJobObject(IntPtr security, string name);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool SetInformationJobObject(IntPtr job,int info,ref ExtendedLimits limits,int length);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool IsProcessInJob(IntPtr process,IntPtr job,out bool result);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcessW(string app,StringBuilder command,IntPtr processSecurity,IntPtr threadSecurity,bool inherit,uint flags,IntPtr environment,string directory,ref StartupInfo startup,out ProcessInfo info);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern IntPtr CreateFileW(string file,uint access,uint share,ref SecurityAttributes security,uint creation,uint attributes,IntPtr template);
        [DllImport("kernel32.dll", SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
        [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access,bool inherit,int pid);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetProcessTimes(IntPtr process,out long creation,out long exit,out long kernel,out long user);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool QueryFullProcessImageNameW(IntPtr process,uint flags,StringBuilder name,ref int length);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool TerminateProcess(IntPtr process,uint code);
        [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
        [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
        [DllImport("ntdll.dll")] static extern int NtQuerySystemInformation(int information,IntPtr buffer,int length,out int needed);
        IntPtr job;
        public ProcessJob() {
            job=CreateJobObject(IntPtr.Zero,null);
            if(job==IntPtr.Zero) throw new Win32Exception();
            var limits=new ExtendedLimits(); limits.Basic.Flags=0x2000; // KILL_ON_JOB_CLOSE
            if(!SetInformationJobObject(job,9,ref limits,Marshal.SizeOf(limits))) {
                int error=Marshal.GetLastWin32Error(); Dispose(); throw new Win32Exception(error);
            }
        }
        public static string Quote(string argument) {
            var result=new StringBuilder("\""); int slashes=0;
            foreach(char value in argument) {
                if(value=='\\') { slashes++; continue; }
                result.Append('\\', value=='"' ? slashes*2+1 : slashes);
                result.Append(value); slashes=0;
            }
            result.Append('\\',slashes*2); result.Append('"'); return result.ToString();
        }
        public static Identity LaunchOwner(string executable,string[] arguments,string directory) {
            // No inherited pipe handles: a caller using redirected output must
            // receive EOF when start.ps1 ends, even while the owner keeps running.
            var command=new StringBuilder(Quote(executable));
            foreach(string argument in arguments) command.Append(" ").Append(Quote(argument));
            var startup=new StartupInfo {Size=Marshal.SizeOf(typeof(StartupInfo))};
            ProcessInfo info;
            if(!CreateProcessW(executable,command,IntPtr.Zero,IntPtr.Zero,false,0x08000000,IntPtr.Zero,directory,ref startup,out info)) throw new Win32Exception();
            try { return ReadIdentity(info.Process,(int)info.ProcessId); }
            finally { CloseHandle(info.Thread); CloseHandle(info.Process); }
        }
        static Identity ReadIdentity(IntPtr process,int pid) {
            long creation,exit,kernel,user;
            if(!GetProcessTimes(process,out creation,out exit,out kernel,out user)) throw new Win32Exception();
            var name=new StringBuilder(32768); int length=name.Capacity;
            if(!QueryFullProcessImageNameW(process,0,name,ref length)) throw new Win32Exception();
            return new Identity {ProcessId=pid,CreationTime=creation.ToString(CultureInfo.InvariantCulture),ImagePath=name.ToString()};
        }
        public static Identity Snapshot(int pid) {
            IntPtr handle=OpenProcess(0x101000,false,pid);
            if(handle==IntPtr.Zero) {
                int error=Marshal.GetLastWin32Error();
                if(error==87) return null;
                // A reused PID may belong to a process this user cannot open.
                if(error==5) return Listed(pid);
                throw new Win32Exception(error);
            }
            try {
                if(WaitForSingleObject(handle,0)==0) return null;
                try { return ReadIdentity(handle,pid); }
                catch { if(WaitForSingleObject(handle,0)==0) return null; return Listed(pid); }
            }
            finally { CloseHandle(handle); }
        }
        // Creation time from the kernel process list, which needs no process
        // handle. ImagePath stays null, so a matching creation time alone is
        // never accepted as identity; a different one proves PID reuse.
        static Identity Listed(int pid) {
            int length=1<<20;
            while(true) {
                IntPtr buffer=Marshal.AllocHGlobal(length);
                try {
                    int needed;
                    int status=NtQuerySystemInformation(5,buffer,length,out needed);
                    if(status==unchecked((int)0xC0000004)) { length=Math.Max(length*2,needed+65536); continue; }
                    if(status<0) throw new InvalidOperationException("Process list unavailable: 0x"+status.ToString("X8",CultureInfo.InvariantCulture));
                    for(int offset=0;;) {
                        IntPtr entry=IntPtr.Add(buffer,offset);
                        if(Marshal.ReadIntPtr(entry,IntPtr.Size==8 ? 80 : 68).ToInt64()==pid)
                            return new Identity {ProcessId=pid,CreationTime=Marshal.ReadInt64(entry,32).ToString(CultureInfo.InvariantCulture)};
                        int next=Marshal.ReadInt32(entry);
                        if(next==0) return null;
                        offset+=next;
                    }
                } finally { Marshal.FreeHGlobal(buffer); }
            }
        }
        // The same kernel handle is used for revalidation and termination, closing
        // the PID-reuse race between a command-line check and Stop-Process.
        public static void StopVerified(int pid,string creation,string image) {
            IntPtr handle=OpenProcess(0x101001,false,pid);
            if(handle==IntPtr.Zero) {
                int error=Marshal.GetLastWin32Error(); if(error==87) return;
                throw new Win32Exception(error);
            }
            try {
                if(WaitForSingleObject(handle,0)==0) return;
                Identity current;
                try { current=ReadIdentity(handle,pid); }
                catch { if(WaitForSingleObject(handle,0)==0) return; throw; }
                // A different creation time proves the recorded process already
                // exited and its PID was reused: nothing to stop, never touch it.
                if(current.CreationTime!=creation) return;
                if(!String.Equals(current.ImagePath,image,StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Process identity changed; refusing termination.");
                if(!TerminateProcess(handle,0)) {
                    if(WaitForSingleObject(handle,0)==0) return;
                    throw new Win32Exception();
                }
                if(WaitForSingleObject(handle,10000)!=0) throw new InvalidOperationException("Process did not exit.");
            } finally { CloseHandle(handle); }
        }
        public Identity Spawn(string executable,string[] arguments,string directory,string log) {
            var security=new SecurityAttributes {Length=Marshal.SizeOf(typeof(SecurityAttributes)),Inherit=true};
            IntPtr output=CreateFileW(log,0x40000000,3,ref security,1,0x80,IntPtr.Zero);
            if(output==new IntPtr(-1)) throw new Win32Exception();
            IntPtr input=CreateFileW("NUL",0x80000000,3,ref security,3,0x80,IntPtr.Zero);
            var startup=new StartupInfo {Size=Marshal.SizeOf(typeof(StartupInfo)),Flags=0x100,Input=input,Output=output,Error=output};
            var command=new StringBuilder(Quote(executable));
            foreach(string argument in arguments) command.Append(" ").Append(Quote(argument));
            ProcessInfo info;
            try {
                if(!CreateProcessW(executable,command,IntPtr.Zero,IntPtr.Zero,true,0x08000004,IntPtr.Zero,directory,ref startup,out info)) throw new Win32Exception();
            } finally { CloseHandle(output); if(input!=new IntPtr(-1)) CloseHandle(input); }
            try {
                if(!AssignProcessToJobObject(job,info.Process)) throw new Win32Exception();
                var identity=ReadIdentity(info.Process,(int)info.ProcessId);
                if(ResumeThread(info.Thread)==0xffffffff) throw new Win32Exception();
                return identity;
            } catch { TerminateProcess(info.Process,1); throw; }
            finally { CloseHandle(info.Thread); CloseHandle(info.Process); }
        }
        public bool Contains(int pid) {
            IntPtr handle=OpenProcess(0x1000,false,pid); if(handle==IntPtr.Zero) return false;
            try { bool result; return IsProcessInJob(handle,job,out result) && result; }
            finally { CloseHandle(handle); }
        }
        public void Dispose() { if(job!=IntPtr.Zero) { CloseHandle(job); job=IntPtr.Zero; } }
    }
}
