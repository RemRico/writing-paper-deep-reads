---
name: writing-paper-deep-reads
description: Use when the user asks to "精读" / "精读总结" / "深读" / "deep read" an academic paper (arXiv, PDF, or local file) and produce a structured Chinese markdown summary. Triggers on phrases like 精读论文, 帮我精读, 精读总结, 论文精读, "summarize this paper deeply", or when the user drops a PDF and asks for a thorough writeup. Writes a single .md file in the user's research directory following their personal template.
---

# Writing Paper Deep-Reads (精读总结)

## Overview

用户精读论文时，输出一份结构化的中文 markdown：文件名 `{论文简称} 论文精读总结.md`，与 PDF 同目录。文档遵循固定章节骨架，**每张图都配解读**，末尾必有"对自身工作的启发"。

**核心原则**：忠实复现用户已有文档风格——不发明新结构、不写英文、不省图解读、不省启发段。

**章节模板**见 `template.md`（写第一节前必读一遍，确保章节顺序与字段不漏）。

### 三种图片来源模式（先判断再进入 Workflow）

| 模式 | 触发条件 | 主要动作 |
|---|---|---|
| **A. 用户附图**（主力） | 用户消息里附带了图像文件（粘贴/拖拽/附件） | **第一动作立刻 cp** `~/.claude/image-cache/{session}/*.png` 到 `images/`（image-cache 有 TTL，晚了就丢，见 Pitfall 7）→ 读 PDF 后视觉匹配 → mv 重命名为 `{slug}-fig{N}.png` |
| **B. 自动抽图**（fallback） | 用户没附图 | 走现有 `scripts/crop_figure.py` 整页渲染路线 |
| **C. 混合** | 用户附了部分图 | A + B 的并集：给了的直接用；识别出的关键图用户没给 → 默认**标 TODO 让用户补**（不要自动抽，除非用户说"剩下你自己抽"） |

**截图是用户观察到的最大时间消耗环节**。优先走模式 A/C，让用户在 crop 上发挥其视觉优势，Claude 负责匹配、命名、嵌入、解读、提醒缺图。

## ⚠️ Known Pitfalls — 实战踩过的坑（先读这一节）

这些坑在过去真实地耗掉过 50%+ 的 token，不要重新交学费。

### 1. 🔴 Read 工具对 PNG 有渲染缓存错位

**现象**：裁好图存到 `images/`，再用 Read 检查时，显示内容与磁盘上 md5 验证过的实际内容不一致。同一文件 cp 到不同路径会显示不同结果。会导致你反复怀疑裁剪坐标错了 → 重新裁 → 再 Read → 再不对，循环 8-10 轮。

**对策**：
- **永远不要把 Read 的 image preview 当作 ground truth**
- 校验 crop 结果用 **file size + md5** 为准（`scripts/crop_figure.py` 会自动打印 md5）
- 必须用 Read 看的话：先 `cp images/xxx.png /tmp/$(date +%s)_xxx.png` 到全新路径再 Read
- 若 Read 结果和你预期不符，第一反应是"缓存错位"，不是"我裁错了"

### 2. 🟠 figure 精细裁剪性价比极低——默认整页 PNG

**现象**：靠目测 + 试错调裁剪坐标，一张图调 4 轮是常态。

**对策**：
- **默认策略改为给整页 PNG**（`scripts/crop_figure.py PDF PAGE --out images/xxx.png`），用户自行裁剪
- 图明显只占页面某个区域时用命名区域粗裁（`--region top-half` / `bottom-third` 等），不要手搓像素坐标
- **不要追求像素级精修**——隐含要求"给精修后的 fig" 是假的，用户自己裁成本更低
- 收尾时告诉用户："整页 PNG 放在 images/，若需精剪请用图片工具"

### 3. 🟡 PDF > 20MB 时 Read 会直接失败

**现象**：`PDF file exceeds maximum allowed size of 20MB`，在 21MB 这种临界值也会触发。

**对策**：
- Workflow 第 2 步先 `ls -la PDF`，> 20MB 时**直接跳过 Read，走 pdftoppm 出 PNG** 读取
- 不要先试 Read 再 fallback，省一轮失败

### 4. 🟡 arXiv PDF 物理页顺序常被打乱

**现象**：arXiv 生成的 PDF 物理页号 ≠ 论文逻辑页号（References 可能排在前面、附录插在中间）。

**对策**：
- pdftoppm 按物理页号渲染，判断"这是论文第几页"要**读 PNG 内容**，不要信页号
- 找某张特定 figure 时：先 `pdftoppm` 把前 10-15 页全渲成 PNG，再批量 Read 找到含目标 figure 的页

### 5. 🟢 单次 Write 的 content 上限 < 完整精读文档长度

**现象**：完整精读文档常 >250 行、> 8k 字，单次 Write 可能报输出长度错。

**对策**：长文分段写
1. 首次 Write：头部 + 元信息 + 1-2 章节 + 末尾占位注释 `<!-- [后续章节] -->`
2. 用 Edit 把 `<!-- [后续章节] -->` 替换成接下来的 2-3 章节 + 新占位
3. 重复直到写完，最后一轮把占位注释替换为空
- 每段前先在对话里说"现在写第 X 节"，让用户能中断纠偏

### 6. 🟢 TaskCreate 系统提醒可以忽略

单文档精读任务**不需要 TaskCreate**（会收到多次"consider TaskCreate"提醒）。skill 内工作流本身就是线性的，忽略提醒即可，不要为了安抚它创建无意义任务。

### 7. 🔴 用户附图的 image-cache 有 TTL —— 必须第一时间 cp

**现象**：用户附图（粘贴/拖拽），session jsonl 里会显示 `~/.claude/image-cache/{session-id}/{N}.png`，**这些文件是真实存在的**。但有 TTL —— 经实测：

| 时机 | 结果 |
|---|---|
| call #4 cp（1 Read + 3 Bash 之内） | ✅ 成功 |
| call #6 cp | ✅ 成功 |
| **call #13 cp（7 Reads + 5 Bashes 之后）** | **❌ No such file** |

**机制推测**：Claude Code 把附图同时塞给 multimodal API + 写到 image-cache 磁盘；后者有 TTL（数秒~几十秒？读 PDF 这种重 IO 会拖到超期）。

**对策（关键）**：**接到附图请求后，第一个 Bash 立刻 cp 图，PDF 之后再读。** 顺序错了就丢图。

**第一动作模板**（必须放在 Workflow Step 2 之前执行）：

```bash
# 1) 找最新的 image-cache 目录（即当前 session 的）
LATEST=$(ls -td ~/.claude/image-cache/*/ 2>/dev/null | head -1)
echo "found cache: $LATEST"
ls -la $LATEST

# 2) mkdir 目标 + 一次性全量 cp 到 images/，先用 N.png 占位命名
TARGET="${HOME}/research/{topic}/images"
mkdir -p $TARGET
cp $LATEST/*.png $TARGET/
ls -la $TARGET/*.png
```

cp 完之后，附图已经安全落盘。**之后再 Read PDF + 多模态视觉匹配 + mv 成 canonical 命名**：

```bash
# 后置：根据视觉匹配结果重命名
mv $TARGET/1.png $TARGET/{slug}-fig1.png
mv $TARGET/2.png $TARGET/{slug}-fig2.png
...
```

**降级路径（如果第一时间 cp 也失败）**：
- 检查 `LATEST` 是否真是当前 session 的目录（看 session-id 是否匹配，不确定时 ls 多个 cache 目录看时间戳）
- 如果 cache 真的不可用：走"视觉匹配 + 命名清单"，让用户自己把附图另存为 `images/{slug}-fig{N}.png`
- **绝对不要 fallback 到模式 B 自动从 PDF 抽图** —— 用户截图的劳动作废

## Workflow

```
1. 定位 & 拆题 & 判模式
   ├── 确认 PDF 路径与"论文简称"
   ├── 探查工作目录的调研主题
   ├── 检测用户是否附了图像 → 决定模式 A/B/C
   └── 不确定时问用户

2. 🔴 模式 A/C 时：第一动作 = 立刻 cp 附图到 images/（见 Pitfall 7）
   ├── ls -td ~/.claude/image-cache/*/ | head -1  → 找当前 session cache 目录
   ├── mkdir -p {target}/images
   ├── cp {cache}/*.png {target}/images/        → 先用 N.png 占位命名
   └── 验证 ls 看文件齐全
   ⚠️ 这一步必须在读 PDF 之前做。延迟到 call #10+ 就会 cache miss。

3. 读论文（看 PDF 大小路由）
   ├── ls -la PDF → 先看 size
   ├── ≤ 20MB：Read 直接读，大 PDF 用 pages 参数分段
   └── > 20MB：跳过 Read，pdftoppm 把前 10-15 页渲成 PNG 再读（见 Pitfall 3）
   → 重点抓：标题、作者+机构、arXiv ID/会议、动机、贡献、方法、实验、消融
   → 在脑中列一个"关键图清单"（intro/teaser、architecture、重要定性、重要消融）

4. 图片匹配 & 重命名
   ├── 模式 A/C：multimodal 视觉看每张已 cp 的 N.png + 对照 PDF 匹配到论文 Figure N
   │   ├── 用户说明顺序的（"img1=Fig2"）按其声明
   │   ├── 模糊时问用户
   │   ├── mv {target}/images/N.png {target}/images/{slug}-fig{真实Figure号}.png
   │   └── 关键图用户没给 → .md 里放 TODO 占位 + 收尾报告列"建议补截清单"
   └── 模式 B（无附图）
       └── scripts/crop_figure.py PDF PAGE --out images/{slug}-fig{N}.png --dpi 200

   ⚠️ 绝对禁止：模式 A cp 失败后 fallback 到模式 B 自动抽。先排查 cache 目录对不对，
                再退回"视觉匹配 + 让用户自己另存"，不要丢掉用户的截图劳动。

5. 写文档（长文分段）
   ├── 按 template.md 顺序填章节
   ├── > 250 行预期 → 分 2-3 轮写（Write 头部 + sentinel → Edit 替 sentinel）
   ├── 每张图（含 TODO 占位）后必写"图N解读"段
   │   └── TODO 占位的图也先写"图 N 解读（预读）" —— 基于 PDF 正文 + caption
   ├── 公式 $$...$$ + 直觉理解段双轨
   ├── 主结果表加粗最佳行
   └── 末尾"对自身工作的启发" 必针对当前调研主题写

6. 收尾自检 Output Checklist + 缺图清单
```

4. 写文档（长文分段）
   ├── 按 template.md 顺序填章节
   ├── > 250 行预期 → 分 2-3 轮写（Write 头部 + sentinel → Edit 替 sentinel）
   ├── 每张图（已有 or TODO 占位）后必写"图N解读"段
   │   └── TODO 占位的图也先写"图 N 解读（预读）" —— 基于 PDF 正文 + caption 先写，用户补图后不用大改
   ├── 公式 $$...$$ + 直觉理解段双轨
   ├── 主结果表加粗最佳行
   └── 末尾"对自身工作的启发" 必针对当前调研主题写

5. 收尾
   ├── 自检 Output Checklist
   ├── 告诉用户还差哪些图（模式 A/C 常有），附上页码 + 描述
   └── 模式 B 的整页 PNG 也告诉用户"需要精剪请自行处理"
```

## Conventions（不要破坏）

### 文件命名
- 主文件：`{论文简称} 论文精读总结.md`（中文空格分隔；`_精读总结.md` 下划线版本也可）
- 论文简称用论文中 propose 的方法名；没有就用第一作者姓 + 方法关键词
- 与 PDF 同目录

### 图片命名与存放
- `images/{paper-slug}-fig{N}.png`，slug 小写连字符（如 `paper-a`、`colbert-late-interaction`）
- 编号 fig{N} 对应**论文里的 Figure N**（不是用户给图的顺序 img1/img2）——必要时用户给了 img1/2/3 而论文是 Fig 1/3/5，要按论文编号，不按 img 顺序
- 用户附图：`cp` / `mv` 到 canonical 路径，不保留临时路径和原文件名
- 模式 B 自动抽：用 `scripts/crop_figure.py` 渲染，**不要手写 PIL 像素坐标**
- 缺图占位格式：`<!-- TODO: 插入 {slug}-fig{N}.png（{描述，如"架构图，page N"}）— 建议用户补截 -->`

### 必备格式
| 元素 | 要求 |
|---|---|
| 图 | 每张图必跟"图 N 解读"段（分点 + 关键洞察，不只 OCR caption） |
| 公式 | `$$...$$` 块公式 + "直觉理解"段（把符号翻成人话） |
| 主结果表 | 最佳行加粗（行内 `**值**`），表后跟"关键发现"小段 |
| 元信息 | blockquote：标题/作者+机构/会议或 arXiv/关键词；如需为某位研究者补充身份、背景或别名（同公司同事、知名学者等），可在元信息加粗或括注，便于日后辨识 |
| 文风标记 | ⭐ 关键设计 · ⚠️ 易踩坑 · 📘 前置课 · ✅/❌ 对比 · `>` 引用块做澄清 |

### 末尾启发段（必写）
- 必须**针对当前调研主题**，不能泛泛而谈
- 调研主题判断顺序：路径名 → 同目录 .md → 问用户

## Output Checklist

- [ ] 文件名 = `{论文简称} 论文精读总结.md`，与 PDF 同目录
- [ ] H1 + blockquote 元信息齐全，必要时为关键人物加粗或括注身份
- [ ] 至少有：动机、方法详解、实验设置、主结果、消融、启发
- [ ] 每张图（含 TODO 占位）都有"图 N 解读"段
- [ ] 公式后有"直觉理解"段
- [ ] 主结果表的最佳行加粗
- [ ] 启发段针对当前调研主题
- [ ] 图片用 `images/{paper-slug}-fig{N}.png` 相对路径；fig 编号对应论文 Figure 编号，不是 img 顺序
- [ ] 模式 A/C：用户没给的关键图已标 TODO，收尾报告里列了"建议补截清单"（含页码 + 描述）
- [ ] 模式 A/C：**第一动作**已 cp 附图到 `images/`（不是先读 PDF 后再 cp，那样 cache 已过 TTL）
- [ ] 模式 B：整页 PNG 就位，收尾时告诉用户"需精剪请自行处理"
- [ ] 没有用 Read 的 PNG preview 当 ground truth 来"验证"裁剪结果

## When NOT to Use

- 用户只问"这篇论文讲什么"/"帮我看一眼" → 浅读 1-2 段即可
- 用户要 PPT / 邮件 / 思维导图 / draft 笔记 → 不是精读总结
- 用户明确要英文 summary → 本 skill 默认中文

## Common Mistakes

| 错误 | 正确做法 |
|---|---|
| 贴图但不写"图N解读" | 每张图必有解读段，分点 + 关键洞察 |
| 启发段写"该方法可借鉴"空话 | 必须针对当前调研主题写"具体怎么迁移到我们 X 任务" |
| 用英文连字符/下划线替换中文文件名 | 默认 `{论文简称} 论文精读总结.md` |
| 占位符全堆末尾 TODO | 占位放在该图本该出现的位置 |
| 公式后直接接表格 | 公式必跟"直觉理解"段 |
| 追求像素级精裁 figure | 默认整页 PNG，精剪交给用户 |
| 用 Read 的 image preview 验证 crop | 用 md5 + file size；Read preview 不可信（见 Pitfall 1） |
| 大 PDF 硬试 Read | > 20MB 直接 pdftoppm 路线（见 Pitfall 3） |
| 为单文档任务建 TaskCreate 安抚系统提醒 | 忽略提醒；精读本身是线性流程 |
| 用户附图时仍自动抽剩下的图 | 模式 C 默认不补抽，标 TODO 让用户决定；除非用户明说"剩下的你自己抽" |
| 按 img 顺序给 fig 编号（用户给 img1/2/3 就叫 fig1/2/3） | fig{N} 对应**论文 Figure 编号**，按论文实际 Figure 号命名 |
| 用户附图后不提醒缺了哪几张关键图 | 收尾报告必须列"建议补截清单"（含页码 + 描述），让用户决定是否补 |
| 用户附图 → 先读 PDF 再 cp → 失败 → fallback 模式 B 自动抽 | ❌ 顺序错了。**第一动作就 cp**，PDF 之后再读。image-cache 有 TTL（call #10+ 必失败）。见 Pitfall 7 |
| 用 jsonl 里写的 image-cache 完整路径 cp（带 session-id） | 用 `ls -td ~/.claude/image-cache/*/ \| head -1` 找当前最新 cache 目录更可靠 |
