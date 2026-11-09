"""Small public Darwin API boundary. No Glyphs objects or subprocesses."""
import ctypes as C
import os
import sys
from threading import Event


class Usage(C.Structure):
    _fields_ = [('uuid', C.c_uint8 * 16)] + [(name, C.c_uint64) for name in (
        'user', 'system', 'idle', 'interrupts', 'pageins', 'wired', 'resident',
        'footprint', 'started', 'exited')]


class DarwinResources:
    def __init__(self, pressure_changed):
        if sys.platform != 'darwin':
            raise OSError('Darwin resource monitoring is unavailable on this platform.')
        self.lib = C.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
        self.lib.proc_pid_rusage.argtypes = [C.c_int, C.c_int, C.c_void_p]
        self.lib.proc_pid_rusage.restype = C.c_int
        self.source = None
        self.cancelled = Event()
        self.callback_type = C.CFUNCTYPE(None, C.c_void_p)
        self.event = self.callback_type(lambda _: self._pressure(pressure_changed))
        self.cancel = self.callback_type(lambda _: self.cancelled.set())
        self.lib.dispatch_get_global_queue.argtypes = [C.c_long, C.c_ulong]
        self.lib.dispatch_get_global_queue.restype = C.c_void_p
        self.lib.dispatch_source_create.argtypes = [C.c_void_p, C.c_size_t, C.c_ulong, C.c_void_p]
        self.lib.dispatch_source_create.restype = C.c_void_p
        self.lib.dispatch_source_get_data.argtypes = [C.c_void_p]
        self.lib.dispatch_source_get_data.restype = C.c_ulong
        for name in ('dispatch_source_set_event_handler_f', 'dispatch_source_set_cancel_handler_f'):
            getattr(self.lib, name).argtypes = [C.c_void_p, self.callback_type]
        for name in ('dispatch_resume', 'dispatch_source_cancel', 'dispatch_release'):
            getattr(self.lib, name).argtypes = [C.c_void_p]

    def subscribe(self):
        kind = C.addressof(C.c_byte.in_dll(self.lib, '_dispatch_source_type_memorypressure'))
        source = self.lib.dispatch_source_create(kind, 0, 1 | 2 | 4,
                                                self.lib.dispatch_get_global_queue(-2, 0))
        if not source:
            raise OSError('Memory-pressure notifications are unavailable.')
        self.source = source
        self.lib.dispatch_source_set_event_handler_f(source, self.event)
        self.lib.dispatch_source_set_cancel_handler_f(source, self.cancel)
        self.lib.dispatch_resume(source)

    def _pressure(self, changed):
        try:
            flags = self.lib.dispatch_source_get_data(self.source)
            changed('critical' if flags & 4 else 'warning' if flags & 2 else 'normal' if flags & 1 else 'unknown')
        except Exception:
            # Exceptions must never escape a ctypes callback into libdispatch.
            changed('unknown')

    def footprint(self):
        usage = Usage()
        if self.lib.proc_pid_rusage(os.getpid(), 0, C.byref(usage)) != 0:
            raise OSError(C.get_errno(), 'Could not read the Glyphs physical footprint.')
        return dict(bytes=usage.footprint, processId=os.getpid(), processStarted=usage.started)

    def close(self):
        if self.source:
            self.lib.dispatch_source_cancel(self.source)
            # Keep callback references alive until libdispatch acknowledges cancellation.
            self.cancelled.wait()
            self.lib.dispatch_release(self.source)
            self.source = None
