# 反调试脚本模板

## 1. 360 Jiagu (freeze-exit) — ✅ 实测稳定

唯一经过实战验证的方案。核心思路：jiagu 的反调试线程通过 libc `exit`/`kill` 杀进程，把该线程冻结在 `while(true) Thread.sleep` 循环里。

```javascript
(function installAntiDebug() {
    var libc = Process.findModuleByName("libc.so");
    if (!libc) return;

    libc.enumerateExports().forEach(function(exp) {
        // strstr — 隐藏 frida 字符串
        if (exp.name === "strstr") {
            Interceptor.attach(exp.address, {
                onEnter: function(args) { try { this.n = args[1].readCString(); } catch(e) {} },
                onLeave: function(retval) {
                    if (this.n && /frida|gadget|xposed|linjector|gdbus|gum|gmain|substrate/i.test(this.n))
                        retval.replace(ptr(0));
                }
            });
        }
        // fopen/open — 重定向 /proc/self/
        if (exp.name === "fopen" || exp.name === "open") {
            Interceptor.attach(exp.address, {
                onEnter: function(args) {
                    try { var p = args[0].readCString(); if (p && p.indexOf("/proc/self/") >= 0) args[0] = Memory.allocUtf8String("/dev/null"); } catch(e) {}
                }
            });
        }
        // ptrace — 返回 0
        if (exp.name === "ptrace") {
            Interceptor.attach(exp.address, { onLeave: function(retval) { retval.replace(ptr(0)); } });
        }
        // ★ 关键：exit/kill/syscall
        if (["exit","_exit","_Exit","kill","tgkill","raise","abort","__exit","syscall"].indexOf(exp.name) >= 0) {
            Interceptor.attach(exp.address, {
                onEnter: function(args) {
                    if (this._fn === "syscall") {
                        var nr = args[0].toInt32();
                        if ([93,94,129,130,131].indexOf(nr) >= 0) args[0] = ptr(172);
                    } else if (this._fn === "kill" || this._fn === "tgkill") {
                        args[1] = ptr(0);
                    } else {
                        while(true) { Thread.sleep(0.1); }
                    }
                }.bind({_fn: exp.name})
            });
        }
    });
})();
```

## 2. 代码级 patch jiagu 反调试函数 — ⚠️ 有风险

直接把 jiagu 的反调试函数入口 patch 为 `mov x0, #0; ret`。比 Interceptor 更隐蔽但偏移必须匹配当前版本。

```javascript
// ARM64: mov x0, #0; ret
var nopRet = new Uint8Array([0x00, 0x00, 0x80, 0xd2, 0xc0, 0x03, 0x5f, 0xd6]);

function patchJiagu() {
    var jiaguMod = null;
    Process.enumerateModules().forEach(function(m) { if (/jiagu/i.test(m.name)) jiaguMod = m; });
    if (!jiaguMod) return;

    // 偏移需要通过 IDA Pro 针对当前版本确认
    var antiFuncs = [/* 从 IDA 分析获取 */];
    antiFuncs.forEach(function(off) {
        Memory.patchCode(jiaguMod.base.add(off), nopRet.byteLength, function(code) {
            code.writeByteArray(nopRet.buffer);
        });
    });
}
```

**风险**：偏移不匹配会 patch 到正常代码，导致 crash。只作为 freeze-exit 方案的补充。

## 3. 腾讯乐固 — 类似方案

乐固的反调试机制与 360 Jiagu 类似，同样通过 exit/kill 杀进程。freeze-exit 方案适用。

额外注意：
- 乐固可能检查 `/proc/self/maps` 中是否有 frida-agent.so
- 需要额外 hook `openat` 重定向 `/proc/<pid>/maps`
- 可能检查特定端口（不仅是 27042）

## 4. 梆梆安全 — 更激进

梆梆的反调试更复杂：
- 检查线程名（是否有 `gum-js-loop` 等 Frida 线程）
- 检查 maps 文件
- 可能用 `inotify` 监控 `/proc/self/` 文件变化
- 可能直接调用 `syscall` 而不走 libc

建议方案：
1. freeze-exit 作为基础
2. 加 hook `prctl` 设置线程名（隐藏 Frida 线程名）
3. 加 hook `inotify_init`/`inotify_add_watch`（屏蔽文件监控）
4. 考虑用 Frida Gadget 方式注入（比 frida-server 更隐蔽）

## 5. strcmp/strstr 扩展版 — 隐藏更多特征

```javascript
// strcmp + strstr — 隐藏更多关键词
["strstr", "strcmp"].forEach(function(fn) {
    var addr = libc.findExportByName(fn);
    if (addr) {
        Interceptor.attach(addr, {
            onEnter: function(a) { try { this.n = a[1].readCString(); } catch(e) {} },
            onLeave: function(r) {
                if (this.n && /frida|gadget|gum|gmain|linjector|gdbus|xposed|substrate|re\.frida|agent|server|gum-js-loop|pool-frida|linjector4/i.test(this.n))
                    r.replace(ptr(0));
            }
        });
    }
});
```

## 6. connect 端口屏蔽

```javascript
var connectAddr = libc.findExportByName("connect");
if (connectAddr) {
    Interceptor.attach(connectAddr, {
        onEnter: function(a) {
            try {
                if (a[1].readU16() === 2) {
                    var port = (a[1].add(2).readU8() << 8) | a[1].add(3).readU8();
                    if (port === 27042 || port === 27043 || port === 9999) this.block = true;
                }
            } catch(e) {}
        },
        onLeave: function(r) { if (this.block) r.replace(ptr(-1)); }
    });
}
```
