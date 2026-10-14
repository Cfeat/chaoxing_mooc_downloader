# chaoxing_material_dl

超星学习通 / 泛雅 / 各校「智慧树式」门户的 **课程资料区** 批量下载工具。

用 Playwright 打开浏览器，你手动登录一次（学校统一认证 / 扫码均可）；之后可递归进入资料文件夹，交互勾选或按类型批量下载到本地。

> **声明**：仅下载你账号有权限的课程资料，供个人学习备份。请遵守学校与平台规定，合理控制请求频率，勿用于未授权传播或商业用途。

## 功能

- Playwright 可视化登录，会话保存在本地 `.sessions/`
- 递归扫描资料区文件夹，保留目录结构
- 交互选择：`all` / 编号区间 / 按扩展名（如 `pdf`）
- 兼容官方域名与各校门户域名（自动回退接口）
- 依赖与 Chromium 均装在项目目录，不污染全局环境
- 安装脚本默认走国内镜像（阿里云 PyPI + npmmirror Playwright）

## 适用平台

本工具面向 **超星（Chaoxing）学习通 / 泛雅** 技术栈的「课程 → 资料」模块。只要资料列表走同一套 `stu-datalist` / `downloadData` 接口，一般可用。

### 支持较好

| 类型 | 示例 |
|------|------|
| 超星官方 | `*.chaoxing.com`（如 `mooc1.chaoxing.com`、`mooc2-ans.chaoxing.com`、`i.chaoxing.com`） |
| 学校泛雅 / 学习通门户 | `mooc1.s.<学校>.edu.cn`、`mooc1.<学校>.edu.cn` 等 |

常见使用学校门户入口登录的课程（统一认证跳转超星）也适用：登录时把 **学校课程页完整 URL** 传给 `login --url` 即可。

### 当前范围（请注意）

| 支持 | 暂不支持 |
|------|----------|
| 课程 **「资料 / 课件」** 区文件与子文件夹 | 章节任务点里的视频 / 附件（非资料区） |
| PDF / PPT / Word / Excel / 压缩包等常见附件 | 个人云盘大文件、作业提交附件 |
| 登录态复用、按类型筛选批量下 | 自动刷课、签到、答题 |

若老师把文件只挂在「章节任务点」而不放进「资料」，本工具扫不到——这是范围限制，不是登录失败。

### 如何判断你的课能不能用

1. 浏览器打开课程，能看到 **资料**（或「课件资料」）页签  
2. 地址栏含 `courseid`、`clazzid`、`cpi` 参数  
3. 域名是超星官方或学校 `mooc*.edu.cn` 类门户  

满足以上三点，即可尝试。

## 环境要求

- Python **3.10+**
- Windows / macOS / Linux
- 能弹出图形界面浏览器（登录步骤需要）

## 安装

依赖装在项目内 `.venv`，Chromium 装在 `.playwright-browsers/`。

### Windows

```powershell
cd chaoxing_material_dl
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### macOS / Linux

```bash
cd chaoxing_material_dl
bash setup.sh
chmod +x run.sh   # 首次如需要
```

镜像说明：

- PyPI：`https://mirrors.aliyun.com/pypi/simple/`
- Playwright 浏览器：`https://npmmirror.com/mirrors/playwright`

## 快速开始

### Windows（PowerShell 请用 `run.ps1`）

> 不要用 `run.bat` 传带 `&` 的课程 URL：PowerShell/cmd 会把 `&` 拆成多条命令。请用 `.\run.ps1`，或运行后按提示粘贴链接。

```powershell
# 1. 登录（推荐直接贴学校课程页）
.\run.ps1 login --url "https://mooc1.s.example.edu.cn/...?courseid=...&clazzid=...&cpi=..."

# 2. 交互下载
.\run.ps1 download --url "同一课程URL"

# 或先登录后不带 URL，按提示粘贴 / 从课程列表选择
.\run.ps1 download
```

### macOS / Linux

```bash
./run.sh login --url "https://..."
./run.sh download --url "https://..."
```

### 选择文件时的输入

| 输入 | 含义 |
|------|------|
| `all` / `*` | 全部下载 |
| `1,3,5-9` | 按编号（可区间） |
| `pdf` / `.pptx` | 按类型 / 扩展名 |
| `q` | 取消 |

### 批量示例

```powershell
.\run.ps1 download --url "..." --all
.\run.ps1 download --url "..." --select pdf
.\run.ps1 download --url "..." --select 1,2,5-8 --out D:\课件
```

```bash
./run.sh download --url "..." --all
./run.sh download --url "..." --select pdf
```

### 其他命令

```text
status     查看是否已登录
logout     清除本地会话
courses    列出我的课程
list       只打印资料树，不下载
```

## 常用参数

| 参数 | 说明 |
|------|------|
| `--url` | 课程页完整链接（含 `courseid` / `clazzid` / `cpi`） |
| `--course-id` `--clazz-id` `--cpi` | 不传 URL 时手动指定 |
| `--out` | 下载根目录，默认 `./downloads` |
| `--flat` | 不保留文件夹层级 |
| `--depth` | 文件夹下钻最大深度，默认 12 |
| `--interval` | 请求间隔（秒），默认 0.3 |
| `-v` | 打印扫描过程 |

## 目录结构

```text
chaoxing_material_dl/
├── chaoxing_dl/           # 源代码
├── setup.ps1 / setup.sh   # 安装（国内镜像）
├── run.ps1 / run.bat / run.sh
├── requirements.txt
├── downloads/             # 默认下载目录（git 忽略）
├── .sessions/             # 登录态（git 忽略，勿分享）
├── .venv/                 # 本地 Python 环境（git 忽略）
└── .playwright-browsers/  # 本地 Chromium（git 忽略）
```

## 常见问题

**会话失效**  
重新执行 `login`。

**`'clazzid' 不是内部或外部命令`（Windows）**  
URL 中的 `&` 被 shell 拆开了。改用 `.\run.ps1`，或运行 `download` 后按提示粘贴完整链接。

**资料区是空的**  
确认文件在「资料」而不是仅在章节任务点；本工具当前只扫资料区。

**下载 403**  
CDN 需正确 Referer；工具已处理。仍失败时重新登录再试。

**学校 SSO 无法登录官方 i.chaoxing.com**  
`login --url` 请直接使用学校课程页链接。

