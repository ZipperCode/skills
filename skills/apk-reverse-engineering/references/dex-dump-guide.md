# DEX 脱壳详细指南

## 何时需要脱壳

- Java hook 无法捕获签名参数（阶段 2 P0/P0b 全空）
- 签名逻辑可能在 native 层实现
- 需要静态分析完整的业务代码（如阅读 `addExtraParams` 方法源码）
- DEX 类 dump 返回 ClassNotFoundException（DEX 尚未解密或类不在当前加载的 DEX 中）

## 方法 1：frida-dexdump（推荐）

最简单的脱壳方式：

```bash
pip install frida-dexdump

# attach 到运行中的进程（必须先装反调试 hook）
frida-dexdump -H 127.0.0.1:<port> -p <PID> -o ./dumped_dex/

# 反编译
jadx -d ./jadx_out ./dumped_dex/*.dex
```

**注意事项**：
- frida-dexdump 在加固进程中被杀的风险很高——必须先装反调试
- dump 期间如果进程被杀，尝试更短时间窗口（减少 dump 时间）
- 多个 DEX 可能存在（主 DEX + 业务分包 DEX），全部都要 dump
- **parse_dex.py 解析的是 stub DEX（加固壳），不是业务 DEX**——必须用 frida-dexdump 或手动 dump

## 方法 2：手动内存扫描 DEX

创建 `dump_dex.js` 脚本：

```javascript
function dumpDex() {
    var dexMagic = [0x64, 0x65, 0x78, 0x0a]; // "dex\n"
    var ranges = Process.enumerateRanges('r--');
    var dexFiles = [];

    ranges.forEach(function(range) {
        try {
            var header = range.base.readByteArray(4);
            var bytes = new Uint8Array(header);
            if (bytes[0] === dexMagic[0] && bytes[1] === dexMagic[1] &&
                bytes[2] === dexMagic[2] && bytes[3] === dexMagic[3]) {
                // 读 DEX 文件大小（偏移 32-35）
                var size = range.base.add(32).readU32();
                if (size > 0 && size < range.size) {
                    var dexData = range.base.readByteArray(size);
                    dexFiles.push({base: range.base, size: size, data: dexData});
                    console.log("[DEX] Found at 0x" + range.base.toString(16) + " size=" + size);
                }
            }
        } catch(e) {}
    });

    // 写入文件到设备
    dexFiles.forEach(function(dex, i) {
        try {
            var ctx = Java.use("android.app.ActivityThread").currentApplication().getApplicationContext();
            var path = ctx.getFilesDir().getAbsolutePath() + "/dumped_dex_" + i + ".dex";
            var fos = Java.use("java.io.FileOutputStream").$new(path);
            fos.write(Java.array('byte', dex.data));
            fos.close();
            console.log("[WROTE] " + path);
        } catch(e) { console.log("[DEX WRITE ERR] " + e); }
    });
}
```

## 方法 3：Frida Gadget 注入

如果 frida-server 方式不稳定，考虑使用 Frida Gadget：

1. 将 `frida-gadget-android-arm64.so.xz` 解压并重命名为任意名字（如 `libtest.so`）
2. 放入 APK 的 `lib/arm64-v8a/` 目录
3. 在 APK 的 `smali` 中找一个在启动时执行的类，添加 `System.loadLibrary("test")` 调用
4. 重打包 APK 并签名
5. Gadget 会自动监听端口（默认 27042），或通过配置文件指定

**优势**：Gadget 在 jiagu DEX 解密前就已注入，可以更早 hook  
**劣势**：需要重打包 APK，可能触发更多检测

## 反编译工具选择

| 工具 | 适用场景 |
|---|---|
| jadx | 最推荐，支持多 DEX、混淆还原、搜索 |
| dex2jar + JD-GUI | 传统方案，对 jadx 失败的 DEX 可作为备选 |
| apktool | 提取资源和 smali，不是反编译但可用于修改 APK |
| Ghidra | 分析 native SO 文件（IDA Pro 的免费替代） |
| IDA Pro | 最强大的 native 分析工具（本次用 IDA 定位了 jiagu 反调试偏移） |

## DEX 加密常见模式

| 加固 | DEX 加密方式 | dump 策略 |
|---|---|---|
| 360 Jiagu | `.jiagu/` 目录存储加密 DEX，运行时由 `libjiagu_64.so` 解密到内存 | 等进程内存 >100MB 后 dump |
| 腾讯乐固 | 类似 Jiagu，`libshella-2.10.so` 解密 | 等内存稳定后 dump |
| 梆梆安全 | 多层加密，可能使用自定义加载器 | 更难 dump，考虑 Gadget 方案 |
| 百度加固 | `libbaiduprotect.so` 解密 | 类似 Jiagu 策略 |

**通用原则**：等 DEX 解密完成后再 dump。判断依据：进程内存从 ~50MB 增长到 >100MB 且稳定。
