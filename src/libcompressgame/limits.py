"""Native subprocess memory limits on the two supported targets."""
from __future__ import annotations

import ctypes
import os

from .common import ArchiveError


def spawn_options(memory_bytes):
    if os.name == 'nt':
        return {}
    def set_limit():
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    return {'preexec_fn': set_limit}


class WindowsMemoryJob:
    """A per-process committed-memory cap; handle closure terminates surviving children."""
    def __init__(self, process, memory_bytes):
        self.handle = None
        if os.name != 'nt':
            return
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [('ProcessTime', ctypes.c_int64), ('JobTime', ctypes.c_int64),
                        ('LimitFlags', w.DWORD), ('MinWorkingSet', ctypes.c_size_t),
                        ('MaxWorkingSet', ctypes.c_size_t), ('ActiveProcesses', w.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', w.DWORD),
                        ('SchedulingClass', w.DWORD)]
        class Counters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('Basic', Basic), ('IO', Counters), ('ProcessMemoryLimit', ctypes.c_size_t),
                        ('JobMemoryLimit', ctypes.c_size_t), ('PeakProcessMemory', ctypes.c_size_t),
                        ('PeakJobMemory', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.CloseHandle.argtypes = [w.HANDLE]
        kernel.CloseHandle.restype = w.BOOL
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ArchiveError(f'CreateJobObject failed: {ctypes.get_last_error()}')
        info = Extended()
        info.Basic.LimitFlags = 0x100 | 0x2000  # PROCESS_MEMORY | KILL_ON_JOB_CLOSE
        info.ProcessMemoryLimit = memory_bytes
        if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.get_last_error()
            self.close()
            raise ArchiveError(f'Setting decoder memory cap failed: {error}')
        if not kernel.AssignProcessToJobObject(self.handle, w.HANDLE(int(process._handle))):
            error = ctypes.get_last_error()
            self.close()
            if process.poll() is not None:
                return  # The child completed before job attachment; no work remains to cap.
            raise ArchiveError(f'Assigning decoder memory cap failed: {error}')

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
