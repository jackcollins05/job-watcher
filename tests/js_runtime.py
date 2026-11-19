"""Execute local pure JavaScript: Node on CI, in-process JavaScriptCore on macOS.

No browser, DOM, network, package installation, or OS automation is used.
"""
import ctypes
import ctypes.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def evaluate(expression):
    scripts = '\n'.join((ROOT / 'js' / name).read_text() for name in ('common.js','browse.js','charts.js','market.js','today.js'))
    program = scripts + '\n(function(){\n' + expression + '\n})()'
    node = shutil.which('node')
    if node:
        # Fixed local evaluation only; fixture data never requests URLs. Popen is
        # deliberate: the suite blocks subprocess.run to prevent accidental curl.
        with subprocess.Popen([node, '-e', 'const source=require("node:fs").readFileSync(0,"utf8");Promise.resolve(eval(source)).then(v=>process.stdout.write(JSON.stringify(v))).catch(e=>{console.error(e);process.exitCode=1;})'],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
            out, error = proc.communicate(program, timeout=30)
            if proc.returncode:
                raise AssertionError(error)
        return json.loads(out)
    if sys.platform != 'darwin':
        raise AssertionError('Frontend tests require Node.js (available on GitHub runners) or macOS JavaScriptCore.')
    lib = ctypes.CDLL('/System/Library/Frameworks/JavaScriptCore.framework/JavaScriptCore')
    ptr = ctypes.c_void_p
    signatures = {
        'JSGlobalContextCreate': ([ptr],ptr), 'JSGlobalContextRelease': ([ptr],None),
        'JSStringCreateWithUTF8CString': ([ctypes.c_char_p],ptr),
        'JSStringRelease': ([ptr],None),
        'JSEvaluateScript': ([ptr,ptr,ptr,ptr,ctypes.c_int,ctypes.POINTER(ptr)],ptr),
        'JSValueToStringCopy': ([ptr,ptr,ctypes.POINTER(ptr)],ptr),
        'JSStringGetMaximumUTF8CStringSize': ([ptr],ctypes.c_size_t),
        'JSStringGetUTF8CString': ([ptr,ctypes.c_char_p,ctypes.c_size_t],ctypes.c_size_t),
    }
    for name,(args,result) in signatures.items():
        fn = getattr(lib,name); fn.argtypes=args; fn.restype=result
    context = lib.JSGlobalContextCreate(None)
    wrapped = 'globalThis.__done=false; Promise.resolve(eval(' + json.dumps(program) + ')).then(v=>{globalThis.__value=JSON.stringify(v);globalThis.__done=true;},e=>{globalThis.__error=String(e);globalThis.__done=true;});'
    script = lib.JSStringCreateWithUTF8CString(wrapped.encode())
    def string(value):
        text = lib.JSValueToStringCopy(context,value,None)
        try:
            size = lib.JSStringGetMaximumUTF8CStringSize(text)
            buffer = ctypes.create_string_buffer(size)
            lib.JSStringGetUTF8CString(text,buffer,size)
            return buffer.value.decode()
        finally:
            lib.JSStringRelease(text)
    try:
        error = ptr()
        value = lib.JSEvaluateScript(context,script,None,None,1,ctypes.byref(error))
        if error.value:
            raise AssertionError(string(error))
        result_script = lib.JSStringCreateWithUTF8CString(b'if (!globalThis.__done) throw new Error("Unsettled test promise"); if (globalThis.__error) throw new Error(globalThis.__error); globalThis.__value;')
        try:
            value = lib.JSEvaluateScript(context,result_script,None,None,1,ctypes.byref(error))
            if error.value:
                raise AssertionError(string(error))
            return json.loads(string(value))
        finally:
            lib.JSStringRelease(result_script)
    finally:
        lib.JSStringRelease(script)
        lib.JSGlobalContextRelease(context)
