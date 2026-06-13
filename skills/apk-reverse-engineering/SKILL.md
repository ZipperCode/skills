---
name: apk-reverse-engineering
description: "APK 逆向工程技能——用于对 Android APK 进行动态分析、反调试绕过、运行时 Hook 捕获签名算法。适用场景：逆向 APK 的 API 签名算法（如 c_key、sign、token）、破解加密参数、dump 加固 DEX。触发时机：用户提到 '逆向 APK'、'逆向签名算法'、'Hook Android'、'Frida APK'、'反调试绕过'、'加固 dump'、'c_key'、'sign 算法'、'Android 逆向'、'抓签名参数'、'脱壳'、'dump DEX' 时使用此技能，即使用户没有明确说'逆向'但描述的任务涉及分析 Android 应用加密参数也应触发。"
---

# APK 逆向工程技能

对 Android APK 进行系统性逆向分析——从反调试绕过到签名算法捕获的完整闭环。

## 为什么需要这个技能

Android APK 的 API 签名算法逆向有四个核心挑战，每个都需要专门的处理：

1. **加固反调试**：360 Jiagu、腾讯乐固、梆梆等加固会检测 Frida/Xposed 并杀进程
2. **方法名猜不准**：加固后的 DEX 中类名/方法名可能被混淆，猜错一个就全断
3. **算法可能比预期简单**：盲爆 763 种变体不如运行时捕获一次真实明文
4. **dex 可能未解密**：attach 太早 DEX 还在加密状态，Java.use 会 ClassNotFoundException

## 执行流程

按以下四个阶段顺序推进。每个阶段都有明确的决策点，不要跳阶段。

### 阶段 0：环境准备

1. 确认设备连接和 frida-server 运行：
   ```
   adb shell ps -A | grep <frida-server-name>
   adb shell ps -A | grep <target-package>
   adb forward tcp:<port> tcp:<port>
   frida-ps -H 127.0.0.1:<port> | grep <target>
   ```
2. 确认目标进程 PID 和内存大小（>100MB 通常表示 DEX 已解密）
3. 如果 frida-server 断了，用 `adb shell su -c 'nohup /data/local/tmp/<server> -l 0.0.0.0:<port> &'` 重启
4. **注意**：加固壳可能改变进程名（如 360 Jiagu 显示为 `dkplayer-ui`），按 PID 或进程名搜索

### 阶段 1：侦查（解决"方法名猜不准"）

**这是最关键的阶段**——所有后续 hook 都依赖此阶段的发现。

创建 `recon_dump.js` 脚本，核心功能：

1. **目标类详细 dump**——方法 + 字段 + 构造器 + 静态字段值：
   - 对每个已知类（如 `NetImpl`、`NetBuilder`、签名相关类）dump 全部声明
   - **重点读静态字段值**——KEY/SALT 可能直接存在静态字段中（本次 C_KEY 就是从 `NetImpl.C_KEY` 读到的）
   - 修复 `java.lang.reflect.Modifier` 引用 → 用 `Java.use("java.lang.reflect.Modifier")`

2. **全量类枚举**——找出被混淆/猜漏的类：
   - `Java.enumerateLoadedClassesSync()` 过滤目标包名 `com.xxx.*`
   - 标记可疑工具类：正则 `MD5|Sign|Crypt|Digest|Secur|Hash|Hmac|Cipher|Token|Encode`
   - **特别注意拼写变体**：`ohter` vs `other`，`ohter` vs `other`，混淆器常用这种防搜索手法

3. **builder 运行时探测**——hook 签名注入方法，在内部反射参数的真实类型：
   - 对 `addExtraParams(builder)` 的参数调用 `getClass().getDeclaredMethods()/getDeclaredFields()`
   - 打印 builder 的真实读参方法名和字段值（可能直接看到 c_key）

**反调试**：参考下方"反调试方案"章节，v4（while(true) freeze-exit）是唯一稳定方案。

**执行**：
```bash
frida -H 127.0.0.1:<port> -p <PID> -l recon_dump.js -o recon_dump.txt
```

**决策点 D1**（读 recon_dump.txt）：
- builder 字段直接含 `c_key=...` → 阶段 2 直接读字段
- 拿到真实方法名（如 `getParams()`/`getBody()`）→ 阶段 2 精准 hook
- 某些类 NOT LOADED → 多等几秒重跑，或在全量枚举找真实包名
- **混淆类名发现**（如 `ohter.MD5`）→ 立刻更新阶段 2 的 hook 目标

### 阶段 2：捕获（多点覆盖）

创建 `capture_ckey.js` 脚本，注入点按优先级排列：

| 优先级 | 注入点 | 要点 |
|---|---|---|
| P0a | `MessageDigest.update([B)` + `digest()` + `digest([B)` | 累积 update 内容，digest 时合并。只在 algo==MD5 记录。用 hashCode 关联 update/digest 对象 |
| P0b | 自定义 MD5 工具类（阶段1发现的真实类名） | 入参即拼好的明文（最干净），包所有 overload |
| P1 | 签名注入方法（如 `addExtraParams(builder)`） | 读注入前后参数 diff。用阶段1发现的真实方法名读参数 |
| P1b | 网络配置的 `onBeforeRequest(builder)` | 签名注入的入口方法 |

**所有注入点**都要打印：输入明文 + 输出 hex + Java 调用栈（`Log.getStackTraceString(Throwable.$new())`）

**关键技术决策**：

1. **主动触发请求**——不依赖用户交互：
   - 创建 NetBuilder 并调用 start，带已知 c_id
   - 这比等用户点击更可靠（app 在后台可能不发请求）
   - 也可 `am force-stop + monkey` 重启 app 抓启动请求

2. **不要杀进程**——`am force-stop` 会杀掉 Frida session。用 attach 模式，不杀 app

**执行**：
```bash
frida -H 127.0.0.1:<port> -p <PID> -l capture_ckey.js -o capture_run.txt
```

**决策点 D2**（读 capture_run.txt）：
- P0a/P0b MD5 命中（IN 含 c_key 相关参数 + OUT == 抓包值）→ 阶段 3
- 只 P0b 自定义 MD5 命中 → 入参即明文，直接复现
- P1 有 c_key 但 P0 全空 → c_key 在 native 算 → 阶段 4 Fallback

### 阶段 3：离线复现验证

用捕获的真实明文 + 输出，创建 `reverse_v7.py`：

1. **自洽性**：验证 `md5(IN) == OUT`（不一致试 latin-1 / 检查 url-encode）
2. **模板重建**：对比真实明文 vs 已知 body 参数，多出的固定段 = KEY/盐，参数顺序 = 真实拼接顺序
3. **验证**：用重建的模板对所有已知样本计算，**全部 == expected 即完成**
4. **注意编码**：URL-encode 前后、参数顺序、KEY 位置（与 RMUTGF_KEY XOR 0x10 交叉验证）

### 阶段 4：Fallback（仅当阶段 2 全空）

按从轻到重尝试：

- **4A native MD5 hook**：hook `libcrypto.so` 的 `MD5_Update`/`MD5_Final`
- **4B 直接抓 KEY**：hook 解密函数 + 内存扫描 KEY 串
- **4C 脱壳 dump DEX**：`frida-dexdump` → `jadx` → 直接读源码

---

## 反调试方案

### 唯一稳定方案：while(true) freeze-exit

来自 `capture_ckey_final.js` 实测稳定 1 分钟+ 的方案：

```javascript
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
                    if ([93,94,129,130,131].indexOf(nr) >= 0) args[0] = ptr(172); // → getpid
                } else if (this._fn === "kill" || this._fn === "tgkill") {
                    args[1] = ptr(0); // 信号置 0
                } else {
                    while(true) { Thread.sleep(0.1); } // ★ 冻结 jiagu 的自杀线程
                }
            }.bind({_fn: exp.name})
        });
    }
});
```

### 为什么其他方案不行

| 方案 | 失败原因 |
|---|---|
| fromJiagu 过滤 + 改退出码 | jiagu 内部检测机制不走 libc，直接在内部实现 |
| Memory.patchCode jiagu 偏移 | 偏移可能不匹配当前版本，patch 导致 crash |
| Interceptor.replace exit 为空 | 调用线程继续执行，访问已释放资源导致 crash |
| Frida spawn mode (-f) | 远程 frida-server 不稳定支持 spawn by name |

### 其他加固的处理

- **腾讯乐固**：类似的 exit/kill 检测，freeze-exit 方案同样适用
- **梆梆安全**：更激进的检测，可能需要额外的 maps 文件屏蔽和线程名检查
- **通用建议**：先用 strstr hook 看加固在搜什么关键词，再针对性屏蔽

---

## Frida 17.x API 注意事项

Frida 17.x 有 API 变更，旧脚本可能不兼容：

- `Module.findExportByName("libc.so", name)` → 仍可用但推荐 `Process.getModuleByName("libc.so").findExportByName(name)`
- `Process.getModuleByName()` 找不到模块会抛异常（不像旧版返回 null）
- `libc.enumerateExports()` 比逐个 `findExportByName` 更高效
- `Java.use()` 在 `setTimeout` 回调中可能报 "Java is not defined" → 用 frida CLI `-o` 而非 Python runner
- `args[0]` 在 Interceptor onEnter 中可直接操作，不需要 `Memory.readXXX` 读原始值

---

## 常见坑与避坑指南

| 坑 | 避坑方法 |
|---|---|
| 方法名猜错 | 阶段 1 必须 dump 真实签名后再 hook |
| MD5 类名被混淆 | 全量枚举 + 正则 `MD5|Sign|Crypt|Digest` 搜索 |
| 算法假设过于复杂 | 先用运行时捕获一次真实明文，再推导公式；不要盲爆 |
| DEX 未解密就 hook | 等进程内存 >100MB 后再 attach，或用 setTimeout 延迟 |
| `java.lang.reflect.Modifier` 引用 | 用 `Java.use("java.lang.reflect.Modifier")` 而非直接引用 |
| frida-server 断连 | 每次操作前检查连接状态，断则重启 |
| 进程名被壳改变 | 按 PID attach 或搜索 frida-ps 输出中的陌生名 |
| `getPostMap()` TypeError | 可能是 overload 问题，用反射 `getDeclaredMethod` 检查真实方法签名 |
| 盲爆不收敛 | 算法可能不含 body 参数，只拼接 id + 常量 + KEY |

---

## 脱壳 (DEX Dump) 子流程

当阶段 2 全空（签名逻辑在 native 层或无法通过 Java hook 捕获）时，需要 dump 真实 DEX 进行静态分析。

### frida-dexdump 方式

```bash
pip install frida-dexdump
# attach 到运行中的进程（必须先装反调试）
frida-dexdump -H 127.0.0.1:<port> -p <PID> -o ./dumped_dex/
# 反编译
jadx -d ./jadx_out ./dumped_dex/*.dex
```

### 手动 dump 方式

创建 `dump_dex.js`，在 DEX 解密后通过 `Process.enumerateRanges('r--')` 扫描内存中的 DEX magic header (`0x64 0x65 0x78 0x0a`)，然后写入文件。

**注意**：
- `parse_dex.py` 解析的是 stub DEX（无业务类），dump 出的真 DEX 才是反编译对象
- dump 过程中进程可能被杀——必须先装反调试 hook
- 多个 DEX 可能存在（主 DEX + 业务分包 DEX），全部 dump

---

## 检查清单

每个阶段完成前，确认以下条件：

### 阶段 1 完成
- [ ] 至少 5 个目标类的真实方法签名已 dump
- [ ] 全量枚举完成，可疑工具类已标记
- [ ] builder 参数的真实类型/方法名已探测
- [ ] 静态字段值（尤其是 KEY/SALT）已读取
- [ ] 进程存活超过 30 秒（反调试稳定）

### 阶段 2 完成
- [ ] 至少一个 P0/P0b 注入点捕获到 MD5 IN + OUT
- [ ] OUT 与抓包的 c_key 值一致
- [ ] Java 调用栈完整，确认签名注入链路
- [ ] 明文可解析（能拆分出 c_id、KEY、盐等固定段）

### 阶段 3 完成（最终判据）
- [ ] `md5(重建的plaintext) == 捕获的OUT` 自洽性通过
- [ ] **所有已知样本**计算结果 == expected
- [ ] 输出最终算法文档：公式 + KEY + KEY 来源链路 + 编码方式

---

## 参考文件

详见 `references/` 目录：

- `references/anti-debug-templates.md` — 反调试脚本模板（多种加固方案）
- `references/frida-17x-api.md` — Frida 17.x API 变更速查表
- `references/dex-dump-guide.md` — DEX 脱壳详细指南

实际使用时，按本 SKILL.md 的流程执行，只在需要具体代码模板时才读取 references。
