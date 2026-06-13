# Frida 17.x API 变更速查表

## 模块查找 API

| 旧 API (16.x) | 新 API (17.x) | 说明 |
|---|---|---|
| `Module.findExportByName("libc.so", "exit")` | `Process.getModuleByName("libc.so").findExportByName("exit")` | 17.x 推荐通过 Process 查找 |
| `Module.findExportByName(null, "android_dlopen_ext")` | `Module.findGlobalExportByName("android_dlopen_ext")` | 全局符号用 findGlobalExportByName |
| `Process.findModuleByName("libc.so")` | 仍然可用 | 返回 null 如果不存在 |
| `Process.getModuleByName("libc.so")` | 新增 | 抛异常如果不存在（比 find 更安全） |

**最佳实践**：
- 确定存在的导出用 `getExportByName()`（找不到会抛异常）
- 可能不存在的导出用 `findExportByName()`（找不到返回 null）
- 批量 hook 多个导出用 `module.enumerateExports()` 更高效

## Interceptor API

| 旧 API | 新 API | 说明 |
|---|---|---|
| `Interceptor.attach(Module.findExportByName(...), cb)` | `Interceptor.attach(module.findExportByName(...), cb)` | 模块获取方式变更 |
| `args[0].readCString()` | `args[0].readCString()` | 未变 |
| `Memory.readUtf8String(args[0])` | `args[0].readUtf8String()` 或 `Memory.readUtf8String(args[0])` | 都可用 |

## Java Bridge

| 旧 API | 新 API | 说明 |
|---|---|---|
| `Java.perform(fn)` | 未变 | 异步等待 Java VM |
| `Java.available` | 未变 | 检查 Java 是否可用 |
| `Java.use("java.lang.reflect.Modifier")` | 未变 | 不能直接引用 `java.lang.reflect.Modifier` |
| `Java.enumerateLoadedClassesSync()` | 未变 | 同步枚举 |

**常见问题**：
- `Java is not defined` 在 Python runner 的 `setTimeout` 回调中 → 用 frida CLI `-o` 代替
- `Java.use()` 返回 ClassNotFoundException → DEX 未解密，等几秒或用 setTimeout 延迟

## Memory API

| 旧 API | 新 API | 说明 |
|---|---|---|
| `Memory.allocUtf8String(str)` | 未变 | 仍然可用 |
| `Memory.patchCode(addr, size, fn)` | 未变 | 需要精确偏移，patch 错误会 crash |
| `Thread.backtrace(ctx, Backtracer.ACCURATE)` | 未变 | 用于判断调用来源 |

## frida CLI 用法

```bash
# attach 模式（稳定）
frida -H 127.0.0.1:9999 -p <PID> -l script.js -o output.txt

# spawn 模式（不稳定，远程 server 可能不支持）
frida -H 127.0.0.1:9999 -f <package> -l script.js -o output.txt

# -o 标志：把 console.log 输出写入本地文件（比 Python send/on_message 更可靠）
```

**关键提示**：
- `-o` 只捕获 `console.log()` 输出，不捕获 `send()` 消息
- Python runner 的 `send()` + `on_message` 方式在遇到 `Java` 不可用时有问题
- 推荐优先使用 frida CLI + `-o` 标志
