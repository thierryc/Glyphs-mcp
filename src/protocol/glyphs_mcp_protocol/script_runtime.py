"""Trusted Python invocation and bounded output, used by the native bridge."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
from .scripts import MAX_OUTPUT_CHARS


class BoundedOutput(io.TextIOBase):
    def __init__(self):
        self.text = ''
        self.truncated = False
    def write(self, value):
        value = str(value)
        combined = self.text + value
        self.truncated |= len(combined) > MAX_OUTPUT_CHARS
        self.text = combined[-MAX_OUTPUT_CHARS:]
        return len(value)
    def flush(self):
        pass


class ScriptRuntime:
    def __init__(self, options, *, font=None, targets=None, glyphs=None):
        self.options = deepcopy(options)
        self.code = compile(options['source'], '<glyphs-mcp-script>', 'exec')
        self.buffer = BoundedOutput()
        self.namespace = {'__name__': '__main__' if options['entrypoint'] == 'script' else '__glyphs_mcp_script__',
                          'params': deepcopy(options['params'])}
        self.namespace.update(font=font, targets=targets or [], Glyphs=glyphs)
        self.initialized = False
    @property
    def output(self):
        return ('[earlier output truncated]\n' if self.buffer.truncated else '') + self.buffer.text
    def initialize(self):
        if self.initialized:
            raise RuntimeError('script module cannot execute twice')
        self.initialized = True
        with redirect_stdout(self.buffer), redirect_stderr(self.buffer):
            exec(self.code, self.namespace)
        if self.options['entrypoint'] == 'per_target' and not callable(self.namespace.get('run')):
            raise ValueError('per_target scripts must define run(layer, params, context)')
    def run_target(self, layer, target, index, total):
        with redirect_stdout(self.buffer), redirect_stderr(self.buffer):
            self.namespace['run'](layer, deepcopy(self.options['params']), dict(target, index=index, total=total))
